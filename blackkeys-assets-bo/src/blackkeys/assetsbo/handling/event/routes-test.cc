#include <map>
#include <set>

#include <arrow/api.h>
#include <arrow/io/memory.h>
#include <arrow/util/logging.h>
#include <drogon/drogon.h>
#include <gtest/gtest.h>
#include <parquet/arrow/writer.h>

#include "blackkeys/assetsbo/handling/event/routes/common.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"
#include "blackkeys/assetsbo/storage/timestamp.hpp"

using namespace blackkeys::assetsbo;
using handling::event::Events;
namespace {
std::string Webp(std::size_t size = 20) {
  std::string bytes(size, '\0');
  bytes.replace(0, 4, "RIFF");
  bytes.replace(8, 4, "WEBP");
  return bytes;
}
std::string Fixture(arrow::TimeUnit::type unit = arrow::TimeUnit::NANO,
                    const std::string &zone = "UTC") {
  auto landmark = arrow::struct_({arrow::field("title", arrow::utf8()),
                                  arrow::field("description", arrow::utf8()),
                                  arrow::field("kiosk_id", arrow::utf8())});
  auto schema =
      arrow::schema({arrow::field("title", arrow::utf8()),
                     arrow::field("description", arrow::utf8()),
                     arrow::field("starttime", arrow::timestamp(unit, zone)),
                     arrow::field("endtime", arrow::timestamp(unit, zone)),
                     arrow::field("landmarks", arrow::list(landmark)),
                     arrow::field("tags", arrow::list(arrow::utf8())),
                     arrow::field("image", arrow::binary())},
                    arrow::key_value_metadata({"fixture"}, {"keep"}));
  std::vector<std::shared_ptr<arrow::Array>> arrays;
  for (auto field : schema->fields())
    arrays.push_back(arrow::MakeArrayOfNull(field->type(), 0).ValueOrDie());
  auto table = arrow::Table::Make(schema, arrays);
  auto sink = arrow::io::BufferOutputStream::Create().ValueOrDie();
  ARROW_CHECK_OK(parquet::arrow::WriteTable(
      *table, arrow::default_memory_pool(), sink, 1024,
      parquet::WriterProperties::Builder().build(),
      parquet::ArrowWriterProperties::Builder().store_schema()->build()));
  return sink->Finish().ValueOrDie()->ToString();
}
std::string Add(const std::string &bytes, const std::string &title = "A & B",
                std::optional<std::string> image = Webp()) {
  auto result = storage::AppendRow(
      bytes,
      {{0, title},
       {1, "first description"},
       {2, "2026-10-07T15:00:00Z"},
       {3, "2026-10-07T16:00:00Z"},
       {4, R"([{"title":"Desk","description":"Visit","kiosk_id":"k1"}])"},
       {5, R"(["music","sale"])"},
       {6, "", image}});
  EXPECT_TRUE(result.error.empty()) << result.error;
  return result.bytes;
}
class Store : public storage::ObjectStore {
public:
  std::string bytes;
  int gets = 0, puts = 0;
  std::string get_error, put_error;
  bool missing = false;
  storage::GetOutcome Get(const std::string &key) override {
    EXPECT_EQ(key, "events.parquet");
    ++gets;
    return {bytes, missing, get_error};
  }
  storage::PutOutcome Put(const std::string &key, const std::string &value,
                          const std::string &type) override {
    EXPECT_EQ(key, "events.parquet");
    EXPECT_EQ(type, "application/vnd.apache.parquet");
    ++puts;
    if (put_error.empty())
      bytes = value;
    return {put_error};
  }
  storage::DeleteOutcome Delete(const std::string &) override {
    ADD_FAILURE();
    return {};
  }
};
class EventRoutes : public testing::Test {
protected:
  Store store;
  Events controller;
  void SetUp() override {
    store.bytes = Add(Fixture());
    storage::SetObjectStoreForTesting(&store);
  }
  void TearDown() override { storage::SetObjectStoreForTesting(nullptr); }
  drogon::HttpResponsePtr Call(const std::string &action,
                               const drogon::HttpRequestPtr &req,
                               const std::string &title = "A & B") {
    drogon::HttpResponsePtr response;
    Events::Callback cb = [&](const auto &r) {
      EXPECT_FALSE(response);
      response = r;
    };
    if (action == "create")
      controller.EventsCreate(req, std::move(cb));
    else if (action == "list")
      controller.EventsList(req, std::move(cb));
    else if (action == "details")
      controller.EventsDetails(req, std::move(cb), title);
    else if (action == "update")
      controller.EventsUpdate(req, std::move(cb), title);
    else if (action == "delete")
      controller.EventsDelete(req, std::move(cb), title);
    else
      controller.EventsImage(req, std::move(cb), title);
    EXPECT_TRUE(response);
    return response;
  }
};
drogon::HttpRequestPtr Get() { return drogon::HttpRequest::newHttpRequest(); }
drogon::HttpRequestPtr
Form(std::vector<std::pair<std::string, std::string>> fields) {
  auto req = drogon::HttpRequest::newHttpFormPostRequest();
  for (auto &[key, value] : fields)
    req->setBodyParameter(key, value);
  return req;
}
drogon::HttpRequestPtr
Upload(std::string bytes,
       std::vector<std::pair<std::string, std::string>> fields = {},
       const std::string &field = "image_file") {
  std::string body;
  for (auto &[key, value] : fields)
    body += "--event-boundary\r\nContent-Disposition: form-data; name=\"" +
            key + "\"\r\n\r\n" + value + "\r\n";
  body += "--event-boundary\r\nContent-Disposition: form-data; name=\"" +
          field +
          "\"; filename=\"event.webp\"\r\nContent-Type: image/webp\r\n\r\n" +
          bytes + "\r\n--event-boundary--\r\n";
  auto req = drogon::HttpRequest::newHttpRequest();
  req->setMethod(drogon::Post);
  req->setContentTypeCode(drogon::CT_MULTIPART_FORM_DATA);
  req->addHeader("content-type",
                 "multipart/form-data; boundary=event-boundary");
  req->setBody(body);
  return req;
}
std::shared_ptr<arrow::Table> Read(const std::string &bytes) {
  return storage::OpenParquetTable(bytes).ValueOrDie();
}
std::shared_ptr<arrow::Scalar> Cell(const std::string &bytes, int row,
                                    int column) {
  return Read(bytes)->column(column)->GetScalar(row).ValueOrDie();
}
} // namespace
TEST_F(EventRoutes, CreateUpdateRenameDeleteUseSingleSnapshot) {
  auto before = Read(store.bytes);
  auto create = Call("create", Form({{"title", "New # event"},
                                     {"starttime", "2026-10-08T10:00:00"},
                                     {"endtime", "2026-10-08T11:00:00"},
                                     {"tags", "[\"new\"]"}}));
  EXPECT_EQ(create->statusCode(), drogon::k302Found);
  EXPECT_EQ(create->getHeader("location"),
            "/v1/event/New%20%23%20event/details");
  EXPECT_EQ(store.gets, 1);
  EXPECT_EQ(store.puts, 1);
  EXPECT_TRUE(before->Equals(*Read(store.bytes)->Slice(0, 1), true));
  EXPECT_FALSE(Cell(store.bytes, 1, 6)->is_valid);
  EXPECT_EQ(Cell(store.bytes, 1, 2)->ToString(),
            "2026-10-08 15:00:00.000000000Z");
  EXPECT_EQ(Call("update",
                 Form({{"title", "Renamed"}, {"description", "changed"}}),
                 "New # event")
                ->statusCode(),
            drogon::k302Found);
  EXPECT_EQ(store.gets, 2);
  EXPECT_EQ(store.puts, 2);
  EXPECT_EQ(Call("details", Get(), "New # event")->statusCode(),
            drogon::k404NotFound);
  EXPECT_EQ(Call("delete", Form({}), "Renamed")->statusCode(),
            drogon::k302Found);
  EXPECT_TRUE(before->Equals(*Read(store.bytes), true));
}
TEST_F(EventRoutes, ImagePreservedReplacedClearedAndServedExactly) {
  auto original = Webp();
  auto image = Call("image", Get());
  EXPECT_EQ(image->body(), original);
  EXPECT_EQ(image->contentTypeString(), "image/webp");
  EXPECT_EQ(image->getHeader("cache-control"), "no-store");
  EXPECT_EQ(image->getHeader("content-length"),
            std::to_string(original.size()));
  EXPECT_EQ(
      Call("update", Upload("", {{"description", "edited"}}))->statusCode(),
      drogon::k302Found);
  EXPECT_EQ(Cell(store.bytes, 0, 6)->ToString(),
            Cell(Add(Fixture()), 0, 6)->ToString());
  EXPECT_EQ(Call("update", Upload(Webp(31)))->statusCode(), drogon::k302Found);
  EXPECT_EQ(Call("image", Get())->body(), Webp(31));
  EXPECT_EQ(Call("update", Form({{"remove_image", "1"}}))->statusCode(),
            drogon::k302Found);
  EXPECT_EQ(Call("image", Get())->statusCode(), drogon::k404NotFound);
}
TEST_F(EventRoutes, ExistingLargeImagesRemainViewableAndUntouched) {
  auto bytes = Webp(handling::event::kMaxImageBytes + 1);
  store.bytes = Add(Fixture(), "A & B", bytes);
  EXPECT_EQ(Call("image", Get())->body(), bytes);
  EXPECT_EQ(Call("update", Form({{"description", "edited"}}))->statusCode(),
            drogon::k302Found);
  EXPECT_EQ(Call("image", Get())->body(), bytes);
}
TEST_F(EventRoutes, ConflictsMissingAndInvalidFieldsDoNotWrite) {
  for (auto fields :
       std::vector<std::vector<std::pair<std::string, std::string>>>{
           {{"title", "  "}},
           {{"title", "bad/name"}},
           {{"unknown", "x"}},
           {{"image", "fake"}},
           {{"starttime", "2026-02-30T10:00:00"}},
           {{"endtime", "2026-10-07T09:00:00"}},
           {{"starttime", "2026-10-07T10:00:00Z"}},
           {{"tags", "not JSON"}},
           {{"landmarks", "{}"}},
           {{"remove_image", "maybe"}},
           {{"starttime_fraction", "123"}}})
    EXPECT_EQ(Call("update", Form(fields))->statusCode(),
              drogon::k400BadRequest);
  EXPECT_EQ(Call("create", Form({{"title", "A & B"}}))->statusCode(),
            drogon::k409Conflict);
  EXPECT_EQ(Call("create", Form({{"title", "New"}}))->statusCode(),
            drogon::k400BadRequest);
  EXPECT_EQ(Call("update", Form({}), "missing")->statusCode(),
            drogon::k404NotFound);
  EXPECT_EQ(Call("delete", Form({}), "missing")->statusCode(),
            drogon::k404NotFound);
  store.bytes = Add(store.bytes, "Other");
  EXPECT_EQ(Call("update", Form({{"title", "Other"}}))->statusCode(),
            drogon::k409Conflict);
  store.bytes = Add(store.bytes);
  for (auto action : {"details", "update", "delete", "image"})
    EXPECT_EQ(Call(action, Form({}))->statusCode(), drogon::k409Conflict);
  EXPECT_EQ(store.puts, 0);
}
TEST_F(EventRoutes, InvalidUploadsDoNotWrite) {
  EXPECT_EQ(Call("update", Upload("PNG"))->statusCode(),
            drogon::k400BadRequest);
  EXPECT_EQ(Call("update", Upload(Webp(handling::event::kMaxImageBytes + 1)))
                ->statusCode(),
            drogon::k400BadRequest);
  EXPECT_EQ(
      Call("update", Upload(Webp(), {{"remove_image", "1"}}))->statusCode(),
      drogon::k400BadRequest);
  EXPECT_EQ(Call("update", Upload(Webp(), {}, "logo_file"))->statusCode(),
            drogon::k400BadRequest);
  EXPECT_EQ(Call("create", Upload(Webp(), {{"title", "New"},
                                           {"starttime", "bad"},
                                           {"endtime", "bad"}}))
                ->statusCode(),
            drogon::k400BadRequest);
  EXPECT_EQ(store.puts, 0);
}
TEST_F(EventRoutes, CreateAcceptsImageAndNestedLists) {
  auto response =
      Call("create", Upload(Webp(), {{"title", "New"},
                                     {"starttime", "2026-10-07T10:00"},
                                     {"endtime", "2026-10-07T11:00"},
                                     {"tags", "[\"fun\"]"},
                                     {"landmarks", "[]"}}));
  EXPECT_EQ(response->statusCode(), drogon::k302Found);
  EXPECT_EQ(store.puts, 1);
  EXPECT_EQ(store.gets, 1);
  EXPECT_EQ(Call("image", Get(), "New")->body(), Webp());
  auto tags =
      std::static_pointer_cast<arrow::ListScalar>(Cell(store.bytes, 1, 5));
  ASSERT_EQ(tags->value->length(), 1);
  EXPECT_EQ(tags->value->GetScalar(0).ValueOrDie()->ToString(), "fun");
}
TEST_F(EventRoutes, ReadParseAndWriteErrorsFailClosed) {
  auto before = store.bytes;
  store.put_error = "write failed";
  EXPECT_EQ(Call("update", Form({{"description", "changed"}}))->statusCode(),
            drogon::k502BadGateway);
  EXPECT_EQ(store.bytes, before);
  store.get_error = "read failed";
  EXPECT_EQ(Call("list", Get())->statusCode(), drogon::k502BadGateway);
  store.get_error.clear();
  store.missing = true;
  EXPECT_EQ(Call("create", Get())->statusCode(), drogon::k502BadGateway);
  store.missing = false;
  store.bytes = "broken parquet";
  EXPECT_EQ(Call("list", Get())->statusCode(), drogon::k502BadGateway);
}
TEST_F(EventRoutes, FormsDetailsAndOrderedListRender) {
  store.bytes = Add(store.bytes, "Second");
  std::string list{Call("list", Get())->body()};
  EXPECT_NE(list.find("A &amp; B"), std::string::npos);
  EXPECT_LT(list.find("A &amp; B"), list.find("Second"));
  EXPECT_NE(list.find("/v1/event/A%20%26%20B/details"), std::string::npos);
  auto edit = std::string(Call("update", Get())->body());
  for (auto fragment :
       {"enctype=\"multipart/form-data\"", "name=\"image_file\"",
        "name=\"remove_image\"", "type=\"datetime-local\"",
        "starttime_fraction", "2026-10-07T10:00:00", "America/Lima (UTC−05:00)",
        "<textarea id=\"description\"", "<textarea id=\"tags\"", "href=\"/\"",
        "href=\"/v1/brand/list\"", "href=\"/v1/event/list\""})
    EXPECT_NE(edit.find(fragment), std::string::npos) << fragment;
  EXPECT_EQ(edit.find("name=\"image\""), std::string::npos);
  auto create = std::string(Call("create", Get())->body());
  EXPECT_EQ(create.find("name=\"remove_image\""), std::string::npos);
  auto details = std::string(Call("details", Get())->body());
  EXPECT_NE(details.find("20 bytes"), std::string::npos);
  EXPECT_NE(details.find("data-event-image"), std::string::npos);
  EXPECT_EQ(details.find("type=\"file\""), std::string::npos);
  EXPECT_EQ(store.puts, 0);
}
TEST_F(EventRoutes, FractionalSecondsSurviveBrowserFormAndPartialUpdates) {
  EXPECT_EQ(Call("update", Form({{"starttime", "2026-10-07T10:00:00"},
                                 {"starttime_fraction", "123456789"},
                                 {"endtime", "2026-10-07T10:00:00"},
                                 {"endtime_fraction", "123456790"}}))
                ->statusCode(),
            drogon::k302Found);
  auto before = Cell(store.bytes, 0, 2);
  EXPECT_EQ(before->ToString(), "2026-10-07 15:00:00.123456789Z");
  EXPECT_EQ(Call("update", Form({{"description", "edit"}}))->statusCode(),
            drogon::k302Found);
  EXPECT_TRUE(before->Equals(*Cell(store.bytes, 0, 2)));
}
TEST(EventStorage, RoundTripsAllTimestampUnitsZonesBinaryAndUntouchedCells) {
  for (auto unit : {arrow::TimeUnit::SECOND, arrow::TimeUnit::MILLI,
                    arrow::TimeUnit::MICRO, arrow::TimeUnit::NANO}) {
    for (auto zone : {"", "UTC", "America/Lima"}) {
      auto bytes = Add(Add(Fixture(unit, zone)), "Other", std::nullopt);
      auto before = Read(bytes);
      const auto stored_unit = std::static_pointer_cast<arrow::TimestampType>(
                                   before->schema()->field(2)->type())
                                   ->unit();
      std::string fraction(storage::TimestampDigits(stored_unit), '1');
      std::string timestamp = "2026-10-07T10:00:00" +
                              (fraction.empty() ? "" : "." + fraction) +
                              "-05:00";
      auto changed = storage::ReplaceCells(
          bytes, 0,
          {{2, timestamp}, {6, "", std::string("\0a\0b", 4)}, {5, "[]"}});
      ASSERT_TRUE(changed.error.empty()) << changed.error;
      auto after = Read(changed.bytes);
      EXPECT_TRUE(before->schema()->Equals(*after->schema(), true));
      EXPECT_TRUE(before->Slice(1, 1)->Equals(*after->Slice(1, 1), true));
      EXPECT_EQ(std::static_pointer_cast<arrow::BinaryScalar>(
                    Cell(changed.bytes, 0, 6))
                    ->value->ToString(),
                std::string("\0a\0b", 4));
      EXPECT_EQ(std::static_pointer_cast<arrow::TimestampScalar>(
                    Cell(changed.bytes, 0, 2))
                    ->value,
                storage::ParseTimestamp(timestamp, stored_unit).ValueOrDie());
      auto removed = storage::RemoveRow(changed.bytes, 0);
      EXPECT_TRUE(before->Slice(1, 1)->Equals(*Read(removed.bytes), true));
      auto cleared = storage::ReplaceCells(changed.bytes, 0, {{6, ""}});
      EXPECT_FALSE(Cell(cleared.bytes, 0, 6)->is_valid);
    }
  }
}
TEST(EventStorage, TimestampValidationAndLimaConversion) {
  for (auto bad :
       {"2026-02-29T10:00:00Z", "2026-10-07T24:00:00Z", "2026-10-07T10:00:60Z",
        "2026-10-07T10:00:00", "2026-10-07T10:00:00+24:00"})
    EXPECT_FALSE(storage::ParseTimestamp(bad, arrow::TimeUnit::NANO).ok());
  EXPECT_FALSE(storage::ParseTimestamp("2026-10-07T10:00:00.001Z",
                                       arrow::TimeUnit::SECOND)
                   .ok());
  auto value = storage::ParseTimestamp("1969-12-31T23:59:59.123456789Z",
                                       arrow::TimeUnit::NANO)
                   .ValueOrDie();
  EXPECT_EQ(storage::LimaTimestamp(value, arrow::TimeUnit::NANO),
            "1969-12-31T18:59:59.123456789");
  EXPECT_EQ(
      storage::ParseTimestamp("2026-10-07T10:00:00-05:00",
                              arrow::TimeUnit::SECOND)
          .ValueOrDie(),
      storage::ParseTimestamp("2026-10-07T15:00:00Z", arrow::TimeUnit::SECOND)
          .ValueOrDie());
}
TEST(EventRoutesRegistration, RegistersOnlyExpectedMethodsAndPaths) {
  auto handlers = drogon::app().getHandlersInfo();
  std::map<std::string, std::set<drogon::HttpMethod>> actual;
  for (auto &[path, method, description] : handlers)
    if (path.starts_with("/v1/event/"))
      actual[path].insert(method);
  const std::map<std::string, std::set<drogon::HttpMethod>> expected = {
      {"/v1/event/list", {drogon::Get}},
      {"/v1/event/create", {drogon::Get, drogon::Post}},
      {"/v1/event/{title}/details", {drogon::Get}},
      {"/v1/event/{title}/update", {drogon::Get, drogon::Post}},
      {"/v1/event/{title}/delete", {drogon::Post}},
      {"/v1/event/{title}/image", {drogon::Get}}};
  EXPECT_EQ(actual, expected);
}

TEST_F(EventRoutes, BrowserEmptyFilenameKeepsImageAndAllowsCreate) {
  auto req = Upload("", {{"description", ""}});
  std::string body(req->body());
  auto filename = body.find("filename=\"event.webp\"");
  body.replace(filename, std::string("filename=\"event.webp\"").size(),
               "filename=\"\"");
  req->setBody(body);
  EXPECT_EQ(Call("update", req)->statusCode(), drogon::k302Found);
  EXPECT_EQ(Call("image", Get())->body(), Webp());
  req = Upload("", {{"title", "Browser"},
                    {"description", ""},
                    {"starttime", "2026-10-07T10:00"},
                    {"endtime", "2026-10-07T11:00"},
                    {"tags", ""},
                    {"landmarks", ""}});
  body = std::string(req->body());
  filename = body.find("filename=\"event.webp\"");
  body.replace(filename, std::string("filename=\"event.webp\"").size(),
               "filename=\"\"");
  req->setBody(body);
  EXPECT_EQ(Call("create", req)->statusCode(), drogon::k302Found);
  EXPECT_FALSE(Cell(store.bytes, 1, 6)->is_valid);
}
