#include "blackkeys/assetsbo/handling/event/routes/common.hpp"

#include <algorithm>
#include <cctype>
#include <unordered_map>

#include <arrow/scalar.h>
#include <drogon/MultiPart.h>

#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"
#include "blackkeys/assetsbo/storage/listing.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"
#include "blackkeys/assetsbo/storage/timestamp.hpp"

namespace blackkeys::assetsbo::handling::event {
std::string EventPath(const std::string &title, const std::string &suffix) {
  return "/v1/event/" + brand::EncodePathSegment(title) + "/" + suffix;
}
void SendError(const Callback &callback, drogon::HttpStatusCode status,
               const std::string &message) {
  drogon::HttpViewData data;
  data.insert("title", std::string("Events"));
  data.insert("heading", std::string("Event request failed"));
  data.insert("meta", std::string{});
  data.insert("message", message);
  brand::SendView(callback, status, "error_page", std::move(data));
}
bool ValidTitle(const std::string &title, const Callback &callback) {
  if (std::ranges::all_of(title,
                          [](unsigned char c) { return std::isspace(c); })) {
    SendError(callback, drogon::k400BadRequest,
              "a nonblank event title is required");
    return false;
  }
  if (auto reason = storage::RejectSegment(title, "title")) {
    SendError(callback, drogon::k400BadRequest, *reason);
    return false;
  }
  return true;
}
std::optional<Snapshot> FetchSnapshot(const Callback &callback) {
  auto got = storage::GetObject(kEventsKey);
  if (got.not_found || !got.error.empty()) {
    SendError(callback, drogon::k502BadGateway,
              got.not_found ? "events.parquet not found in bucket" : got.error);
    return std::nullopt;
  }
  auto table = storage::OpenParquetTable(got.body);
  auto parsed = storage::ParseParquetTable(got.body);
  if (!table.ok() || !parsed.error.empty()) {
    SendError(callback, drogon::k502BadGateway,
              table.ok() ? parsed.error : table.status().ToString());
    return std::nullopt;
  }
  auto schema = (*table)->schema();
  int title = schema->GetFieldIndex("title"),
      start = schema->GetFieldIndex("starttime"),
      end = schema->GetFieldIndex("endtime"),
      image = schema->GetFieldIndex("image");
  if (title < 0 || start < 0 || end < 0 || image < 0 ||
      schema->field(title)->type()->id() != arrow::Type::STRING ||
      schema->field(start)->type()->id() != arrow::Type::TIMESTAMP ||
      schema->field(end)->type()->id() != arrow::Type::TIMESTAMP ||
      (schema->field(image)->type()->id() != arrow::Type::BINARY &&
       schema->field(image)->type()->id() != arrow::Type::LARGE_BINARY)) {
    SendError(callback, drogon::k502BadGateway,
              "events schema requires title, starttime/endtime timestamps, and "
              "binary image");
    return std::nullopt;
  }
  for (int c : {start, end}) {
    auto type = std::static_pointer_cast<arrow::TimestampType>(
        schema->field(c)->type());
    for (int64_t r = 0; r < (*table)->num_rows(); ++r) {
      auto scalar = (*table)->column(c)->GetScalar(r);
      if (!scalar.ok()) {
        SendError(callback, drogon::k502BadGateway, scalar.status().ToString());
        return std::nullopt;
      }
      if ((*scalar)->is_valid)
        parsed.table.rows[r][c] = storage::LimaTimestamp(
            std::static_pointer_cast<arrow::TimestampScalar>(*scalar)->value,
            type->unit());
    }
  }
  return Snapshot{std::move(got.body),
                  std::move(parsed.table),
                  *table,
                  title,
                  start,
                  end,
                  image};
}
std::optional<std::size_t> ResolveRow(const Snapshot &snapshot,
                                      const std::string &title,
                                      const Callback &callback) {
  std::optional<std::size_t> match;
  for (std::size_t r = 0; r < snapshot.display.rows.size(); ++r) {
    if (snapshot.display.rows[r][snapshot.title] != title)
      continue;
    if (match) {
      SendError(callback, drogon::k409Conflict,
                "multiple events share this title");
      return std::nullopt;
    }
    match = r;
  }
  if (!match)
    SendError(callback, drogon::k404NotFound, "event not found");
  return match;
}
namespace {
drogon::HttpRequestPtr
NormalizeEmptyUploads(const drogon::HttpRequestPtr &req) {
  const auto &content_type = req->getHeader("content-type");
  auto boundary_at = content_type.find("boundary=");
  if (boundary_at == std::string::npos)
    return req;
  auto boundary = content_type.substr(boundary_at + 9);
  boundary = boundary.substr(0, boundary.find(';'));
  if (boundary.size() >= 2 && boundary.front() == '"' && boundary.back() == '"')
    boundary = boundary.substr(1, boundary.size() - 2);
  if (boundary.empty())
    return req;
  const std::string marker = "--" + boundary;
  const std::string separator = "\r\n" + marker;
  const std::string_view body = req->body();
  std::vector<std::size_t> replacements;
  auto part = body.find(marker);
  while (part != std::string_view::npos) {
    auto header = part + marker.size();
    if (body.substr(header, 2) != "\r\n")
      break;
    header += 2;
    auto next = body.find(separator, header);
    if (next == std::string_view::npos)
      break;
    auto header_end = body.find("\r\n\r\n", header);
    if (header_end != std::string_view::npos && header_end + 4 == next) {
      auto filename = body.find("filename=\"\"", header);
      if (filename != std::string_view::npos && filename < header_end)
        replacements.push_back(filename + 10);
    }
    part = next + 2;
  }
  if (replacements.empty())
    return req;
  // Drogon 1.9.13 rejects the filename="" sent by an unselected browser
  // file input. Name only empty parts for parsing; their content stays empty.
  std::string normalized(body);
  for (auto pos = replacements.rbegin(); pos != replacements.rend(); ++pos)
    normalized.insert(*pos, "unselected");
  auto copy = drogon::HttpRequest::newHttpRequest();
  copy->setMethod(req->getMethod());
  copy->setContentTypeCode(drogon::CT_MULTIPART_FORM_DATA);
  copy->addHeader("content-type", content_type);
  copy->setBody(std::move(normalized));
  return copy;
}
drogon::HttpViewData ViewData(const Snapshot &snapshot,
                              const std::string &heading) {
  drogon::HttpViewData data;
  data.insert("title", std::string("Events"));
  data.insert("heading", heading);
  data.insert("meta", std::string("America/Lima (UTC−05:00)"));
  data.insert("columns", snapshot.display.column_names);
  data.insert("nested_columns", snapshot.display.nested_columns);
  std::vector<int> digits(snapshot.display.column_names.size(), -1);
  for (int c : {snapshot.start, snapshot.end})
    digits[c] =
        storage::TimestampDigits(std::static_pointer_cast<arrow::TimestampType>(
                                     snapshot.arrow->schema()->field(c)->type())
                                     ->unit());
  data.insert("timestamp_digits", digits);
  return data;
}
} // namespace
void ShowRow(const Snapshot &snapshot, std::size_t row, const std::string &view,
             const Callback &callback) {
  auto title = snapshot.display.rows[row][snapshot.title];
  auto data = ViewData(snapshot, title);
  data.insert("row", snapshot.display.rows[row]);
  data.insert("action", EventPath(title, "update"));
  data.insert("back", EventPath(title, "details"));
  data.insert("delete_action", EventPath(title, "delete"));
  data.insert("image_url", EventPath(title, "image"));
  data.insert("image_uploads_enabled", view == "events_edit");
  data.insert("creating", false);
  brand::SendView(callback, drogon::k200OK, view, std::move(data));
}
void ShowCreate(const Snapshot &snapshot, const Callback &callback) {
  auto data = ViewData(snapshot, "Create event");
  data.insert("row",
              std::vector<std::string>(snapshot.display.column_names.size()));
  data.insert("action", std::string("/v1/event/create"));
  data.insert("back", std::string("/v1/event/list"));
  data.insert("image_url", std::string{});
  data.insert("image_uploads_enabled", true);
  data.insert("creating", true);
  brand::SendView(callback, drogon::k200OK, "events_edit", std::move(data));
}
void Save(const storage::MutationOutcome &mutated, const std::string &redirect,
          const Callback &callback) {
  if (!mutated.error.empty()) {
    SendError(callback, drogon::k400BadRequest, mutated.error);
    return;
  }
  auto put = storage::PutObject(kEventsKey, mutated.bytes,
                                "application/vnd.apache.parquet");
  if (!put.error.empty()) {
    SendError(callback, drogon::k502BadGateway, put.error);
    return;
  }
  callback(drogon::HttpResponse::newRedirectionResponse(redirect));
}
void Mutate(const drogon::HttpRequestPtr &req, const Callback &callback,
            const Snapshot &snapshot, std::optional<std::size_t> row) {
  std::unordered_map<std::string, std::string> fields;
  std::optional<std::string> image;
  if (req->contentType() == drogon::CT_MULTIPART_FORM_DATA) {
    drogon::MultiPartParser parser;
    auto multipart_request = NormalizeEmptyUploads(req);
    if (parser.parse(multipart_request) != 0) {
      SendError(callback, drogon::k400BadRequest, "invalid multipart form");
      return;
    }
    for (auto &[key, value] : parser.getParameters())
      fields[key] = value;
    bool seen_file = false;
    for (auto &file : parser.getFiles()) {
      if (file.getItemName() != "image_file" || seen_file) {
        SendError(callback, drogon::k400BadRequest,
                  "only one image_file upload is supported");
        return;
      }
      seen_file = true;
      auto bytes = file.fileContent();
      if (bytes.empty())
        continue;
      if (auto reason = brand::ValidateWebpUpload(bytes, kMaxImageBytes)) {
        SendError(callback, drogon::k400BadRequest, *reason);
        return;
      }
      image = std::string(bytes);
    }
  } else {
    for (auto &[key, value] : req->getParameters())
      fields[key] = value;
  }
  for (auto &[key, value] : fields) {
    bool fraction = key == "starttime_fraction" || key == "endtime_fraction";
    if (key == "remove_image" || fraction)
      continue;
    auto c = snapshot.arrow->schema()->GetFieldIndex(key);
    if (c < 0 || c == snapshot.image) {
      SendError(callback, drogon::k400BadRequest,
                "unsupported event field: " + key);
      return;
    }
  }
  bool remove = false;
  if (auto f = fields.find("remove_image"); f != fields.end()) {
    if (f->second != "1" && f->second != "on" && f->second != "true" &&
        f->second != "0" && f->second != "false") {
      SendError(callback, drogon::k400BadRequest, "invalid remove_image value");
      return;
    }
    remove = f->second == "1" || f->second == "on" || f->second == "true";
  }
  if (remove && image) {
    SendError(callback, drogon::k400BadRequest,
              "cannot replace and clear the image together");
    return;
  }
  std::string title = row ? snapshot.display.rows[*row][snapshot.title] : "";
  if (fields.contains("title"))
    title = fields["title"];
  if (!ValidTitle(title, callback))
    return;
  for (std::size_t r = 0; r < snapshot.display.rows.size(); ++r)
    if ((!row || r != *row) &&
        snapshot.display.rows[r][snapshot.title] == title) {
      SendError(callback, drogon::k409Conflict,
                "an event with this title already exists");
      return;
    }
  std::vector<storage::CellEdit> edits;
  std::vector<storage::NewCell> cells;
  auto add = [&](int column, const std::string &text,
                 std::optional<std::string> bytes = std::nullopt) {
    edits.push_back({static_cast<std::size_t>(column), text, bytes});
    cells.push_back({static_cast<std::size_t>(column), text, bytes});
  };
  __int128 instants[2];
  int i = 0;
  for (int c : {snapshot.start, snapshot.end}) {
    auto name = snapshot.display.column_names[c];
    auto value = fields.contains(name)
                     ? fields[name]
                     : (row ? snapshot.display.rows[*row][c] : "");
    if (value.size() == 16)
      value += ":00";
    if (fields.contains(name + "_fraction")) {
      if (!fields.contains(name) || value.find('.') != std::string::npos) {
        SendError(callback, drogon::k400BadRequest,
                  "fraction needs a datetime without fractional seconds");
        return;
      }
      auto fraction = fields[name + "_fraction"];
      if (!fraction.empty() &&
          !std::ranges::all_of(
              fraction, [](unsigned char ch) { return std::isdigit(ch); })) {
        SendError(callback, drogon::k400BadRequest,
                  "invalid fractional seconds");
        return;
      }
      if (!fraction.empty())
        value += "." + fraction;
    }
    value += "-05:00";
    auto type = std::static_pointer_cast<arrow::TimestampType>(
        snapshot.arrow->schema()->field(c)->type());
    auto parsed = storage::ParseTimestamp(value, type->unit());
    if (!parsed.ok()) {
      SendError(callback, drogon::k400BadRequest,
                name + ": " + parsed.status().ToString());
      return;
    }
    int64_t scale = 1;
    for (int d = storage::TimestampDigits(type->unit()); d < 9; ++d)
      scale *= 10;
    instants[i++] = static_cast<__int128>(*parsed) * scale;
    if (!row || fields.contains(name))
      add(c, value);
  }
  if (instants[1] <= instants[0]) {
    SendError(callback, drogon::k400BadRequest,
              "endtime must be after starttime");
    return;
  }
  for (auto &[key, value] : fields) {
    int c = snapshot.arrow->schema()->GetFieldIndex(key);
    if (c >= 0 && c != snapshot.start && c != snapshot.end &&
        c != snapshot.image)
      add(c, value);
  }
  if (image)
    add(snapshot.image, "", image);
  else if (remove)
    add(snapshot.image, "");
  Save(row ? storage::ReplaceCells(snapshot.bytes, *row, edits)
           : storage::AppendRow(snapshot.bytes, cells),
       EventPath(title, "details"), callback);
}
} // namespace blackkeys::assetsbo::handling::event
