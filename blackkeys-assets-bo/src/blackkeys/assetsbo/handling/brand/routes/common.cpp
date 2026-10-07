#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include <algorithm>
#include <iterator>
#include <memory>
#include <utility>

#include <json/json.h>

#include "blackkeys/assetsbo/storage/s3.hpp"

namespace blackkeys::assetsbo::handling::brand {

namespace {

std::string HtmlEscape(const std::string &text) {
  return drogon::HttpViewData::htmlTranslate(text);
}

std::string JsonValueToHtml(const Json::Value &value);

std::string JsonObjectToHtml(const Json::Value &value) {
  std::string html = "<table class=\"nested\"><tbody>";
  for (const auto &member : value.getMemberNames()) {
    html += "<tr><th>" + HtmlEscape(member) + "</th><td>" +
            JsonValueToHtml(value[member]) + "</td></tr>";
  }
  html += "</tbody></table>";
  return html;
}

std::string JsonArrayToHtml(const Json::Value &value) {
  if (value.empty()) {
    return "<span class=\"note\">(empty)</span>";
  }

  bool all_objects = true;
  for (const auto &element : value) {
    if (!element.isObject()) {
      all_objects = false;
      break;
    }
  }

  if (!all_objects) {
    std::string html = "<table class=\"nested\"><tbody>";
    for (const auto &element : value) {
      html += "<tr><td>" + JsonValueToHtml(element) + "</td></tr>";
    }
    html += "</tbody></table>";
    return html;
  }

  std::vector<std::string> columns;
  for (const auto &element : value) {
    for (const auto &member : element.getMemberNames()) {
      if (std::ranges::find(columns, member) == columns.end()) {
        columns.push_back(member);
      }
    }
  }

  std::string html = "<table class=\"nested\"><thead><tr>";
  for (const auto &column : columns) {
    html += "<th>" + HtmlEscape(column) + "</th>";
  }
  html += "</tr></thead><tbody>";
  for (const auto &element : value) {
    html += "<tr>";
    for (const auto &column : columns) {
      html += "<td>" +
              (element.isMember(column) ? JsonValueToHtml(element[column])
                                        : std::string()) +
              "</td>";
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return html;
}

std::string JsonValueToHtml(const Json::Value &value) {
  if (value.isNull()) {
    return "null";
  }
  if (value.isObject()) {
    return JsonObjectToHtml(value);
  }
  if (value.isArray()) {
    return JsonArrayToHtml(value);
  }
  if (value.isString()) {
    return HtmlEscape(value.asString());
  }
  if (value.isBool()) {
    return value.asBool() ? "true" : "false";
  }
  if (value.isIntegral()) {
    return std::to_string(value.asLargestInt());
  }
  if (value.isDouble()) {
    return std::to_string(value.asDouble());
  }
  return HtmlEscape(value.toStyledString());
}

} // namespace

bool IsImageKind(std::string_view kind) {
  return kind == "logo" || kind == "picture";
}

std::string BrandImageKey(const std::string &name, std::string_view kind) {
  return "brands/name=" + name + "/" + std::string(kind) + ".webp";
}

std::string EncodePathSegment(const std::string &value) {
  auto encoded = drogon::utils::urlEncodeComponent(value);
  std::size_t pos = 0;
  while ((pos = encoded.find('+', pos)) != std::string::npos) {
    encoded.replace(pos, 1, "%20");
    pos += 3;
  }
  return encoded;
}

std::optional<std::string> ValidateWebpUpload(std::string_view bytes, std::size_t maximum_bytes) {
  if (bytes.size() > maximum_bytes) {
    return "WebP images must be at most " + std::to_string(maximum_bytes / (1024 * 1024)) + " MiB";
  }
  // A WebP file is a RIFF container: "RIFF", 4-byte length, then "WEBP".
  if (bytes.size() < 12 || bytes.substr(0, 4) != "RIFF" ||
      bytes.substr(8, 4) != "WEBP") {
    return "uploaded images must have a valid WebP signature";
  }
  return std::nullopt;
}

void SendView(const Callback &callback, drogon::HttpStatusCode status,
              const std::string &view, drogon::HttpViewData data) {
  auto response = drogon::HttpResponse::newHttpViewResponse(view, data);
  response->setStatusCode(status);
  callback(response);
}

void SendError(const Callback &callback, drogon::HttpStatusCode status,
               const std::string &heading, const std::string &message) {
  drogon::HttpViewData data;
  data.insert("title", std::string("Brands"));
  data.insert("heading", heading);
  data.insert("meta", assetsbo::storage::BucketName());
  data.insert("message", message);
  SendView(callback, status, "error_page", std::move(data));
}

std::optional<storage::ParquetTable> FetchBrandsTable(const Callback &callback) {
  const auto got = assetsbo::storage::GetObject(kBrandsKey);
  if (got.not_found) {
    SendError(callback, drogon::k502BadGateway, "Get failed",
              "brands.parquet not found in bucket");
    return std::nullopt;
  }
  if (!got.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Get failed", got.error);
    return std::nullopt;
  }

  auto parsed = assetsbo::storage::ParseParquetTable(got.body);
  if (!parsed.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Parse failed", parsed.error);
    return std::nullopt;
  }
  return std::move(parsed.table);
}

std::optional<std::size_t> NameColumnIndex(const storage::ParquetTable &table,
                                           const Callback &callback) {
  const auto it =
      std::ranges::find(table.column_names, std::string("name"));
  if (it == table.column_names.end()) {
    SendError(callback, drogon::k502BadGateway, "Missing column",
              "brands.parquet has no 'name' column");
    return std::nullopt;
  }
  return static_cast<std::size_t>(it - table.column_names.begin());
}

std::optional<std::size_t> UniqueRowIndex(const storage::ParquetTable &table,
                                          std::size_t name_idx, const std::string &name,
                                          const Callback &callback) {
  std::optional<std::size_t> found;
  for (std::size_t r = 0; r < table.rows.size(); ++r) {
    if (table.rows[r][name_idx] == name) {
      if (found) {
        SendError(callback, drogon::k409Conflict, "Cannot edit",
                  "editing is disabled while brands share the name \"" + name + "\"");
        return std::nullopt;
      }
      found = r;
    }
  }
  if (!found) {
    SendError(callback, drogon::k404NotFound, "Not found",
              "no brand named \"" + name + "\"");
    return std::nullopt;
  }
  return found;
}

storage::BrandOverrides FetchOverrides() {
  const auto got = assetsbo::storage::GetObject(kOverridesKey);
  if (got.not_found || !got.error.empty()) {
    return {};
  }
  auto parsed = assetsbo::storage::ParseOverrides(got.body);
  if (!parsed.error.empty()) {
    return {};
  }
  return std::move(parsed.overrides);
}

void ApplyOverrides(storage::ParquetTable &table,
                    const storage::BrandOverrides &overrides,
                    std::size_t name_idx) {
  for (auto &row : table.rows) {
    const auto entry = overrides.find(row[name_idx]);
    if (entry == overrides.end()) {
      continue;
    }
    for (const auto &[field, value] : entry->second) {
      if (field == "name") {
        continue;
      }
      const auto col = std::ranges::find(table.column_names, field);
      if (col != table.column_names.end()) {
        row[static_cast<std::size_t>(col - table.column_names.begin())] = value;
      }
    }
  }
}

bool IsOverridden(const storage::BrandOverrides &overrides,
                  const std::string &name, const std::string &field) {
  if (field == "name") {
    return false;
  }
  const auto entry = overrides.find(name);
  return entry != overrides.end() && entry->second.contains(field);
}

std::string RenderNestedCellHtml(const std::string &json_text) {
  Json::Value root;
  Json::CharReaderBuilder builder;
  std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
  std::string errors;
  if (!reader->parse(json_text.data(), json_text.data() + json_text.size(),
                     &root, &errors)) {
    return "<pre>" + HtmlEscape(json_text) + "</pre>";
  }
  return JsonValueToHtml(root);
}

std::optional<BrandMatches> FetchMatches(const std::string &name,
                                         const Callback &callback) {
  auto table = FetchBrandsTable(callback);
  if (!table) {
    return std::nullopt;
  }
  const auto name_idx = NameColumnIndex(*table, callback);
  if (!name_idx) {
    return std::nullopt;
  }

  BrandMatches result;
  result.overrides = FetchOverrides();
  ApplyOverrides(*table, result.overrides, *name_idx);
  for (const auto &row : table->rows) {
    if (row[*name_idx] == name) {
      result.rows.push_back(row);
    }
  }
  result.column_names = std::move(table->column_names);
  result.nested_columns = std::move(table->nested_columns);
  return result;
}

} // namespace blackkeys::assetsbo::handling::brand
