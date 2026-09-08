#include "blackkeys/assetsbo/handling/brand/routes.hpp"
#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include "blackkeys/assetsbo/storage/overrides.hpp"
#include "blackkeys/assetsbo/storage/parquet_table.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"

#include <algorithm>
#include <iterator>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <arrow/array/builder_binary.h>
#include <arrow/io/memory.h>
#include <arrow/table.h>
#include <arrow/util/logging.h>
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>
#include <drogon/UploadFile.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <parquet/arrow/writer.h>

namespace {

drogon::HttpRequestPtr MakeRequest(drogon::HttpMethod method) {
  auto req = drogon::HttpRequest::newHttpRequest();
  req->setMethod(method);
  return req;
}

drogon::HttpRequestPtr MakeFormRequest(
    const std::vector<std::pair<std::string, std::string>> &fields) {
  auto req = drogon::HttpRequest::newHttpFormPostRequest();
  for (const auto &[key, value] : fields) {
    req->setBodyParameter(key, value);
  }
  return req;
}

drogon::HttpRequestPtr MakeUploadRequest(const std::string &field,
                                         const std::string &body,
                                         const std::vector<std::pair<
                                             std::string, std::string>> &fields = {}) {
  const std::string boundary = "assetsbo-test-boundary";
  std::string request_body;
  for (const auto &[key, value] : fields) {
    request_body += "--" + boundary + "\r\n";
    request_body += "Content-Disposition: form-data; name=\"" + key +
                    "\"\r\n\r\n" + value + "\r\n";
  }
  request_body += "--" + boundary + "\r\n"
                  "Content-Disposition: form-data; name=\"" +
      field + "\"; filename=\"image.png\"\r\n"
              "Content-Type: image/png\r\n\r\n";
  request_body += body;
  request_body += "\r\n--" + boundary + "--\r\n";

  auto req = drogon::HttpRequest::newHttpRequest();
  req->setMethod(drogon::Post);
  req->setContentTypeCode(drogon::CT_MULTIPART_FORM_DATA);
  req->addHeader("content-type", "multipart/form-data; boundary=" + boundary);
  req->setBody(std::move(request_body));
  return req;
}

std::string PngBytes(std::size_t size = 8) {
  std::string bytes(size, '\0');
  if (size >= 8) {
    const char signature[] = {'\x89', 'P', 'N', 'G', '\r', '\n', '\x1a', '\n'};
    std::copy(std::begin(signature), std::end(signature), bytes.begin());
  }
  return bytes;
}

std::size_t CountOccurrences(const std::string &text,
                             const std::string &needle) {
  std::size_t count = 0;
  std::size_t position = 0;
  while ((position = text.find(needle, position)) != std::string::npos) {
    ++count;
    position += needle.size();
  }
  return count;
}

std::string BuildBrandsParquet(const std::vector<std::string> &names) {
  arrow::StringBuilder name_builder;
  arrow::StringBuilder phone_builder;
  for (std::size_t i = 0; i < names.size(); ++i) {
    ARROW_CHECK_OK(name_builder.Append(names[i]));
    ARROW_CHECK_OK(phone_builder.Append("phone-" + std::to_string(i)));
  }
  std::shared_ptr<arrow::Array> names_array;
  std::shared_ptr<arrow::Array> phones_array;
  ARROW_CHECK_OK(name_builder.Finish(&names_array));
  ARROW_CHECK_OK(phone_builder.Finish(&phones_array));

  auto table = arrow::Table::Make(
      arrow::schema({arrow::field("name", arrow::utf8()),
                     arrow::field("phone", arrow::utf8())}),
      {names_array, phones_array});
  auto sink = arrow::io::BufferOutputStream::Create().ValueOrDie();
  ARROW_CHECK_OK(parquet::arrow::WriteTable(
      *table, arrow::default_memory_pool(), sink, 1024));
  auto buffer = sink->Finish().ValueOrDie();
  return std::string(reinterpret_cast<const char *>(buffer->data()),
                     buffer->size());
}

struct StoredObject {
  std::string body;
  std::string content_type;
  std::optional<std::string> last_modified;
};

struct PutCall {
  std::string key;
  std::string body;
  std::string content_type;
};

class MemoryObjectStore final
    : public blackkeys::assetsbo::storage::ObjectStore {
public:
  blackkeys::assetsbo::storage::GetOutcome
  Get(const std::string &key) override {
    operations.push_back("get:" + key);
    if (const auto failed = get_errors.find(key); failed != get_errors.end()) {
      return {{}, false, failed->second};
    }
    const auto object = objects.find(key);
    if (object == objects.end()) {
      return {{}, true, {}};
    }
    return {object->second.body, false, {}, object->second.last_modified};
  }

  blackkeys::assetsbo::storage::PutOutcome
  Put(const std::string &key, const std::string &body,
      const std::string &content_type) override {
    operations.push_back("put:" + key);
    puts.push_back({key, body, content_type});
    const auto call = ++put_counts[key];
    if (const auto failed = put_error_on_call.find({key, call});
        failed != put_error_on_call.end()) {
      return {failed->second};
    }
    objects[key] = {body, content_type};
    return {};
  }

  blackkeys::assetsbo::storage::DeleteOutcome
  Delete(const std::string &key) override {
    operations.push_back("delete:" + key);
    deletes.push_back(key);
    if (const auto failed = delete_errors.find(key);
        failed != delete_errors.end()) {
      return {failed->second};
    }
    objects.erase(key);
    return {};
  }

  std::map<std::string, StoredObject> objects;
  std::map<std::string, std::string> get_errors;
  std::map<std::pair<std::string, std::size_t>, std::string>
      put_error_on_call;
  std::map<std::string, std::string> delete_errors;
  std::map<std::string, std::size_t> put_counts;
  std::vector<PutCall> puts;
  std::vector<std::string> deletes;
  std::vector<std::string> operations;
};

class ScopedObjectStore {
public:
  explicit ScopedObjectStore(MemoryObjectStore &store) {
    blackkeys::assetsbo::storage::SetObjectStoreForTesting(&store);
  }
  ~ScopedObjectStore() {
    blackkeys::assetsbo::storage::SetObjectStoreForTesting(nullptr);
  }
};

drogon::HttpResponsePtr UpdateResponse(MemoryObjectStore &store,
                                       const drogon::HttpRequestPtr &req,
                                       const std::string &old_name) {
  ScopedObjectStore scoped(store);
  blackkeys::assetsbo::handling::brand::Brands controller;
  drogon::HttpResponsePtr response;
  controller.BrandsUpdate(
      req, [&response](const drogon::HttpResponsePtr &value) { response = value; },
      old_name);
  return response;
}

} // namespace

using blackkeys::assetsbo::handling::brand::Brands;
using blackkeys::assetsbo::handling::brand::BrandImageKey;
using blackkeys::assetsbo::handling::brand::kBrandsKey;
using blackkeys::assetsbo::handling::brand::kOverridesKey;

TEST(BrandsRoutes, DetailsRejectsBadName) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsDetails(nullptr, callback.AsStdFunction(), "a/b");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
}

TEST(BrandsRoutes, ListFailsWithoutS3Client) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsList(nullptr, callback.AsStdFunction());

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}

TEST(BrandsRoutes, DetailsFailsWithoutS3Client) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsDetails(nullptr, callback.AsStdFunction(), "adidas");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}

TEST(BrandsRoutes, CreateGetFailsWithoutS3Client) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsCreate(MakeRequest(drogon::Get), callback.AsStdFunction());

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}

TEST(BrandsRoutes, CreatePostFailsWithoutS3Client) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsCreate(MakeRequest(drogon::Post), callback.AsStdFunction());

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}

TEST(BrandsRoutes, UpdateRejectsBadName) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsUpdate(nullptr, callback.AsStdFunction(), "a/b");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
}

TEST(BrandsRoutes, UpdateGetFailsWithoutS3Client) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsUpdate(MakeRequest(drogon::Get), callback.AsStdFunction(),
                          "adidas");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}

TEST(BrandsRoutes, UpdatePostFailsWithoutS3Client) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsUpdate(MakeRequest(drogon::Post), callback.AsStdFunction(),
                          "adidas");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}

TEST(BrandsRoutes, ImageRejectsBadName) {
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsImage(
      nullptr,
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "a/b", "logo");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
}

TEST(BrandsRoutes, ImageRejectsUnknownKind) {
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsImage(
      nullptr,
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "adidas", "banner");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
}

TEST(BrandsRoutes, ImageFailsWithoutS3Client) {
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsImage(
      nullptr,
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "adidas", "logo");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}

TEST(BrandsRoutes, ImageReturnsNotFoundForMissingObject) {
  MemoryObjectStore store;
  ScopedObjectStore scoped(store);
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsImage(
      nullptr,
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "adidas", "picture");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k404NotFound);
}

TEST(BrandsRoutes, ImageReturnsPngWithoutCaching) {
  MemoryObjectStore store;
  const auto png = PngBytes(24);
  store.objects[BrandImageKey("adidas", "logo")] = {
      png, "image/png", "Tue, 29 Sep 2026 18:42:15 GMT"};
  ScopedObjectStore scoped(store);
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsImage(
      nullptr,
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "adidas", "logo");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k200OK);
  EXPECT_EQ(response->body(), png);
  EXPECT_EQ(response->contentTypeString(), "image/png");
  EXPECT_EQ(response->getHeader("Cache-Control"), "no-store");
  EXPECT_EQ(response->getHeader("Content-Length"), "24");
  EXPECT_EQ(response->getHeader("Last-Modified"),
            "Tue, 29 Sep 2026 18:42:15 GMT");
}

TEST(BrandsRoutes, ImageOmitsUnavailableLastModified) {
  MemoryObjectStore store;
  const auto png = PngBytes(12);
  store.objects[BrandImageKey("adidas", "picture")] = {png, "image/png"};
  ScopedObjectStore scoped(store);
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsImage(
      nullptr,
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "adidas", "picture");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k200OK);
  EXPECT_EQ(response->body(), png);
  EXPECT_EQ(response->getHeader("Content-Length"), "12");
  EXPECT_TRUE(response->getHeader("Last-Modified").empty());
}

TEST(BrandsRoutes, DetailsHtmlContainsOneSharedImageGridWithoutUploads) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"same name", "same name"}),
                               "application/octet-stream"};
  ScopedObjectStore scoped(store);
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsDetails(
      nullptr,
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "same name");

  ASSERT_TRUE(response);
  ASSERT_EQ(response->statusCode(), drogon::k200OK);
  const std::string html(response->body());
  EXPECT_EQ(CountOccurrences(html, "data-brand-images"), 1);
  EXPECT_EQ(CountOccurrences(html, "data-brand-image=\"logo\""), 1);
  EXPECT_EQ(CountOccurrences(html, "data-brand-image=\"picture\""), 1);
  EXPECT_EQ(CountOccurrences(html, "/v1/brand/same%20name/image/logo"), 1);
  EXPECT_EQ(CountOccurrences(html, "/v1/brand/same%20name/image/picture"), 1);
  EXPECT_NE(html.find("data-image-dimensions"), std::string::npos);
  EXPECT_NE(html.find("Aspect ratio"), std::string::npos);
  EXPECT_NE(html.find("Last modified"), std::string::npos);
  EXPECT_EQ(html.find("type=\"file\""), std::string::npos);
  EXPECT_EQ(html.find("name=\"logo_file\""), std::string::npos);
  EXPECT_EQ(html.find("name=\"picture_file\""), std::string::npos);
}

TEST(BrandsRoutes, EditHtmlContainsMultipartUploadsAndEncodedPreviews) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old name"}),
                               "application/octet-stream"};
  ScopedObjectStore scoped(store);
  Brands controller;
  drogon::HttpResponsePtr response;

  controller.BrandsUpdate(
      MakeRequest(drogon::Get),
      [&response](const drogon::HttpResponsePtr &value) { response = value; },
      "old name");

  ASSERT_TRUE(response);
  ASSERT_EQ(response->statusCode(), drogon::k200OK);
  const std::string html(response->body());
  EXPECT_NE(html.find("enctype=\"multipart/form-data\""), std::string::npos);
  EXPECT_NE(html.find("name=\"logo_file\""), std::string::npos);
  EXPECT_NE(html.find("name=\"picture_file\""), std::string::npos);
  EXPECT_NE(html.find("/v1/brand/old%20name/image/logo"), std::string::npos);
  EXPECT_NE(html.find("/v1/brand/old%20name/image/picture"),
            std::string::npos);
  EXPECT_NE(html.find("data-brand-images"), std::string::npos);
  EXPECT_NE(html.find("data-image-status"), std::string::npos);
  EXPECT_NE(html.find("data-image-size"), std::string::npos);
  EXPECT_NE(html.find("data-image-dimensions"), std::string::npos);
  EXPECT_NE(html.find("data-image-aspect"), std::string::npos);
  EXPECT_NE(html.find("data-image-modified"), std::string::npos);
  EXPECT_NE(html.find("Unsaved replacement"), std::string::npos);
  EXPECT_NE(html.find("Not yet stored"), std::string::npos);
}

TEST(BrandsRoutes, UpdateRejectsEmptySubmittedNameBeforeWrites) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", ""}}), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
  EXPECT_TRUE(store.puts.empty());
}

TEST(BrandsRoutes, UpdateRejectsInvalidSubmittedNameBeforeWrites) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", "a/b"}}), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
  EXPECT_TRUE(store.puts.empty());
}

TEST(BrandsRoutes, UpdateRejectsDuplicateNewNameBeforeWrites) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old", "taken"}),
                               "application/octet-stream"};

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", "taken"}}), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k409Conflict);
  EXPECT_TRUE(store.puts.empty());
}

TEST(BrandsRoutes, RenameRejectsDestinationImageCollisionBeforeWrites) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[BrandImageKey("new", "logo")] = {PngBytes(), "image/png"};

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", "new"}}), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k409Conflict);
  EXPECT_TRUE(store.puts.empty());
}

TEST(BrandsRoutes, RenameWithMissingImagesMovesIdentityAndOverrides) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[kOverridesKey] = {
      R"({"old":{"name":"legacy","phone":"555"},"new brand":{"name":"stale","phone":"stale"}})",
      "application/json"};

  const auto response = UpdateResponse(
      store, MakeFormRequest({{"name", "new brand"}}), "old");

  ASSERT_TRUE(response);
  ASSERT_EQ(response->statusCode(), drogon::k302Found);
  EXPECT_EQ(response->getHeader("Location"),
            "/v1/brand/new%20brand/details");

  const auto parsed_table = blackkeys::assetsbo::storage::ParseParquetTable(
      store.objects.at(kBrandsKey).body);
  ASSERT_TRUE(parsed_table.error.empty()) << parsed_table.error;
  ASSERT_EQ(parsed_table.table.rows.size(), 1u);
  EXPECT_EQ(parsed_table.table.rows[0][0], "new brand");
  EXPECT_EQ(parsed_table.table.rows[0][1], "phone-0");

  ASSERT_EQ(store.puts.size(), 3u);
  EXPECT_EQ(store.puts[0].key, kOverridesKey);
  EXPECT_EQ(store.puts[1].key, kBrandsKey);
  EXPECT_EQ(store.puts[2].key, kOverridesKey);
  const auto transitional = blackkeys::assetsbo::storage::ParseOverrides(
      store.puts[0].body);
  ASSERT_TRUE(transitional.error.empty()) << transitional.error;
  EXPECT_TRUE(transitional.overrides.contains("old"));
  EXPECT_TRUE(transitional.overrides.contains("new brand"));
  EXPECT_FALSE(transitional.overrides.at("old").contains("name"));
  const auto final = blackkeys::assetsbo::storage::ParseOverrides(
      store.puts[2].body);
  ASSERT_TRUE(final.error.empty()) << final.error;
  EXPECT_FALSE(final.overrides.contains("old"));
  ASSERT_TRUE(final.overrides.contains("new brand"));
  EXPECT_FALSE(final.overrides.at("new brand").contains("name"));
  EXPECT_EQ(final.overrides.at("new brand").at("phone"), "555");
  EXPECT_THAT(store.deletes,
              testing::ElementsAre(BrandImageKey("old", "logo"),
                                   BrandImageKey("old", "picture")));
}

TEST(BrandsRoutes, RenameStagesOldImageBeforeIdentityWrites) {
  MemoryObjectStore store;
  const auto png = PngBytes(32);
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[BrandImageKey("old", "logo")] = {png, "image/png"};

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", "new"}}), "old");

  ASSERT_TRUE(response);
  ASSERT_EQ(response->statusCode(), drogon::k302Found);
  ASSERT_GE(store.puts.size(), 4u);
  EXPECT_EQ(store.puts[0].key, BrandImageKey("new", "logo"));
  EXPECT_EQ(store.puts[0].body, png);
  EXPECT_EQ(store.puts[0].content_type, "image/png");
  EXPECT_EQ(store.puts[1].key, kOverridesKey);
  EXPECT_EQ(store.puts[2].key, kBrandsKey);
  EXPECT_EQ(store.puts[3].key, kOverridesKey);
  EXPECT_FALSE(store.objects.contains(BrandImageKey("old", "logo")));
  EXPECT_EQ(store.objects.at(BrandImageKey("new", "logo")).body, png);
}

TEST(BrandsRoutes, RenameRollsBackStagedImagesWhenTransitionalWriteFails) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[BrandImageKey("old", "logo")] = {PngBytes(16), "image/png"};
  store.put_error_on_call[{kOverridesKey, 1}] = "injected failure";

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", "new"}}), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
  EXPECT_FALSE(store.objects.contains(BrandImageKey("new", "logo")));
  EXPECT_TRUE(store.objects.contains(BrandImageKey("old", "logo")));
  const auto parsed_table = blackkeys::assetsbo::storage::ParseParquetTable(
      store.objects.at(kBrandsKey).body);
  ASSERT_TRUE(parsed_table.error.empty()) << parsed_table.error;
  EXPECT_EQ(parsed_table.table.rows[0][0], "old");
}

TEST(BrandsRoutes, RenameRollsBackStagedImagesWhenParquetWriteFails) {
  MemoryObjectStore store;
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[BrandImageKey("old", "logo")] = {PngBytes(16), "image/png"};
  store.put_error_on_call[{kBrandsKey, 1}] = "injected failure";

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", "new"}}), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
  EXPECT_FALSE(store.objects.contains(BrandImageKey("new", "logo")));
  EXPECT_TRUE(store.objects.contains(BrandImageKey("old", "logo")));
  const auto parsed_table = blackkeys::assetsbo::storage::ParseParquetTable(
      store.objects.at(kBrandsKey).body);
  ASSERT_TRUE(parsed_table.error.empty()) << parsed_table.error;
  EXPECT_EQ(parsed_table.table.rows[0][0], "old");
}

TEST(BrandsRoutes, RenameCleanupFailuresStillRedirectToFunctionalNewBrand) {
  MemoryObjectStore store;
  const auto png = PngBytes(16);
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[BrandImageKey("old", "logo")] = {png, "image/png"};
  store.put_error_on_call[{kOverridesKey, 2}] = "injected final failure";
  store.delete_errors[BrandImageKey("old", "logo")] =
      "injected delete failure";

  const auto response =
      UpdateResponse(store, MakeFormRequest({{"name", "new"}}), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k302Found);
  EXPECT_EQ(response->getHeader("Location"), "/v1/brand/new/details");
  const auto parsed_table = blackkeys::assetsbo::storage::ParseParquetTable(
      store.objects.at(kBrandsKey).body);
  ASSERT_TRUE(parsed_table.error.empty()) << parsed_table.error;
  EXPECT_EQ(parsed_table.table.rows[0][0], "new");
  EXPECT_EQ(store.objects.at(BrandImageKey("new", "logo")).body, png);
  EXPECT_TRUE(store.objects.contains(BrandImageKey("old", "logo")));
  const auto transitional = blackkeys::assetsbo::storage::ParseOverrides(
      store.objects.at(kOverridesKey).body);
  ASSERT_TRUE(transitional.error.empty()) << transitional.error;
  EXPECT_TRUE(transitional.overrides.contains("old"));
  EXPECT_TRUE(transitional.overrides.contains("new"));
}

TEST(BrandsRoutes, RenameUsesMultipartFieldsAndUploadedImage) {
  MemoryObjectStore store;
  const auto uploaded = PngBytes(40);
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[BrandImageKey("old", "picture")] = {PngBytes(24),
                                                       "image/png"};

  const auto response = UpdateResponse(
      store,
      MakeUploadRequest("picture_file", uploaded, {{"name", "new"}}),
      "old");

  ASSERT_TRUE(response);
  ASSERT_EQ(response->statusCode(), drogon::k302Found);
  const auto parsed_table = blackkeys::assetsbo::storage::ParseParquetTable(
      store.objects.at(kBrandsKey).body);
  ASSERT_TRUE(parsed_table.error.empty()) << parsed_table.error;
  EXPECT_EQ(parsed_table.table.rows[0][0], "new");
  EXPECT_EQ(store.objects.at(BrandImageKey("new", "picture")).body, uploaded);
  EXPECT_FALSE(store.objects.contains(BrandImageKey("old", "picture")));
}

TEST(BrandsRoutes, UploadParsesMultipartAndWritesPngAfterFieldWrites) {
  MemoryObjectStore store;
  const auto png = PngBytes(64);
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};

  const auto response =
      UpdateResponse(store, MakeUploadRequest("logo_file", png), "old");

  ASSERT_TRUE(response);
  ASSERT_EQ(response->statusCode(), drogon::k302Found);
  EXPECT_EQ(response->getHeader("Location"), "/v1/brand/old/details");
  ASSERT_TRUE(store.objects.contains(BrandImageKey("old", "logo")));
  EXPECT_EQ(store.objects.at(BrandImageKey("old", "logo")).body, png);
  EXPECT_EQ(store.objects.at(BrandImageKey("old", "logo")).content_type,
            "image/png");
  ASSERT_EQ(store.puts.size(), 1u);
  EXPECT_EQ(store.puts[0].key, BrandImageKey("old", "logo"));
}

TEST(BrandsRoutes, UploadRejectsUnknownFileFieldBeforeStorageAccess) {
  MemoryObjectStore store;

  const auto response = UpdateResponse(
      store, MakeUploadRequest("banner_file", PngBytes()), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
  EXPECT_TRUE(store.operations.empty());
}

TEST(BrandsRoutes, UploadRejectsInvalidPngBeforeStorageAccess) {
  MemoryObjectStore store;

  const auto response = UpdateResponse(
      store, MakeUploadRequest("logo_file", "not a png"), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
  EXPECT_TRUE(store.operations.empty());
}

TEST(BrandsRoutes, EmptyUploadPreservesExistingImage) {
  MemoryObjectStore store;
  const auto existing = PngBytes(20);
  store.objects[kBrandsKey] = {BuildBrandsParquet({"old"}),
                               "application/octet-stream"};
  store.objects[BrandImageKey("old", "logo")] = {existing, "image/png"};

  const auto response =
      UpdateResponse(store, MakeUploadRequest("logo_file", ""), "old");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k302Found);
  EXPECT_EQ(store.objects.at(BrandImageKey("old", "logo")).body, existing);
  EXPECT_TRUE(store.puts.empty());
}

TEST(BrandsRoutes, DeleteRejectsBadName) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsDelete(nullptr, callback.AsStdFunction(), "a/b");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k400BadRequest);
}

TEST(BrandsRoutes, DeletePostFailsWithoutS3Client) {
  Brands controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.BrandsDelete(MakeRequest(drogon::Post), callback.AsStdFunction(),
                          "adidas");

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k502BadGateway);
}
