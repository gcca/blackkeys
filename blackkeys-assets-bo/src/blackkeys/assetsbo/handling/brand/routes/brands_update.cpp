#include "blackkeys/assetsbo/handling/brand/routes.hpp"
#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include <algorithm>
#include <array>
#include <optional>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

#include <drogon/MultiPart.h>
#include <trantor/utils/Logger.h>

#include "blackkeys/assetsbo/storage/listing.hpp"
#include "blackkeys/assetsbo/storage/parquet_mutation.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"

namespace blackkeys::assetsbo::handling::brand {
namespace {

using Fields = std::unordered_map<std::string, std::string>;

struct UpdateRequest {
  Fields fields;
  Fields images;
};

struct PendingImage {
  std::string key;
  std::string body;
};

constexpr std::array<std::string_view, 2> kImageKinds = {"logo", "picture"};

void ShowEditForm(const Callback &callback, const std::string &name) {
  auto found = FetchMatches(name, callback);
  if (!found) {
    return;
  }
  if (found->rows.empty()) {
    SendError(callback, drogon::k404NotFound, "Not found",
              "no brand named \"" + name + "\"");
    return;
  }
  if (found->rows.size() > 1) {
    SendError(callback, drogon::k409Conflict, "Cannot edit",
              "editing is disabled while brands share the name \"" + name +
                  "\"");
    return;
  }

  const auto &bucket = assetsbo::storage::BucketName();
  drogon::HttpViewData data;
  data.insert("title", std::string("Brands"));
  data.insert("heading", name);
  data.insert("meta", "s3://" + bucket + "/" + kBrandsKey);
  data.insert("columns", found->column_names);
  data.insert("nested_columns", found->nested_columns);
  data.insert("row", found->rows.front());
  data.insert("image_uploads_enabled", true);
  SendView(callback, drogon::k200OK, "brands_edit", std::move(data));
}

std::optional<UpdateRequest>
ParseUpdateRequest(const drogon::HttpRequestPtr &req, const Callback &callback) {
  UpdateRequest input;
  if (req->contentType() != drogon::CT_MULTIPART_FORM_DATA) {
    for (const auto &[key, value] : req->getParameters()) {
      input.fields[key] = value;
    }
    return input;
  }

  drogon::MultiPartParser parser;
  if (parser.parse(req) != 0) {
    SendError(callback, drogon::k400BadRequest, "Bad upload",
              "could not parse multipart form data");
    return std::nullopt;
  }
  for (const auto &[key, value] : parser.getParameters()) {
    input.fields[key] = value;
  }
  for (const auto &file : parser.getFiles()) {
    const auto &field = file.getItemName();
    std::string kind;
    if (field == "logo_file") {
      kind = "logo";
    } else if (field == "picture_file") {
      kind = "picture";
    } else {
      SendError(callback, drogon::k400BadRequest, "Bad upload",
                "\"" + field + "\" is not a supported file field");
      return std::nullopt;
    }
    if (input.images.contains(kind)) {
      SendError(callback, drogon::k400BadRequest, "Bad upload",
                "only one " + kind + " image may be uploaded");
      return std::nullopt;
    }
    if (file.fileLength() == 0) {
      continue;
    }
    const auto bytes = file.fileContent();
    if (const auto reason = ValidatePngUpload(bytes)) {
      SendError(callback, drogon::k400BadRequest, "Bad upload", *reason);
      return std::nullopt;
    }
    input.images.emplace(kind, bytes);
  }
  return input;
}

std::optional<storage::BrandOverrides>
FetchOverridesStrict(const Callback &callback) {
  const auto got = assetsbo::storage::GetObject(kOverridesKey);
  if (got.not_found) {
    return storage::BrandOverrides{};
  }
  if (!got.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Get failed", got.error);
    return std::nullopt;
  }
  auto parsed = assetsbo::storage::ParseOverrides(got.body);
  if (!parsed.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Parse failed", parsed.error);
    return std::nullopt;
  }
  return std::move(parsed.overrides);
}

std::optional<std::vector<PendingImage>>
PrepareRenameImages(const std::string &old_name, const std::string &new_name,
                    const Fields &uploads, const Callback &callback) {
  for (const auto kind : kImageKinds) {
    const auto got =
        assetsbo::storage::GetObject(BrandImageKey(new_name, kind));
    if (!got.error.empty()) {
      SendError(callback, drogon::k502BadGateway, "Get failed", got.error);
      return std::nullopt;
    }
    if (!got.not_found) {
      SendError(callback, drogon::k409Conflict, "Image conflict",
                BrandImageKey(new_name, kind) + " already exists");
      return std::nullopt;
    }
  }

  std::vector<PendingImage> pending;
  for (const auto kind : kImageKinds) {
    if (const auto upload = uploads.find(std::string(kind));
        upload != uploads.end()) {
      pending.push_back({BrandImageKey(new_name, kind), upload->second});
      continue;
    }

    const auto got =
        assetsbo::storage::GetObject(BrandImageKey(old_name, kind));
    if (!got.error.empty()) {
      SendError(callback, drogon::k502BadGateway, "Get failed", got.error);
      return std::nullopt;
    }
    if (!got.not_found) {
      pending.push_back({BrandImageKey(new_name, kind), got.body});
    }
  }
  return pending;
}

void RemoveStagedImages(const std::vector<std::string> &keys) {
  for (const auto &key : keys) {
    const auto removed = assetsbo::storage::DeleteObject(key);
    if (!removed.error.empty()) {
      LOG_ERROR << "brand rename rollback: failed to delete " << key << ": "
                << removed.error;
    }
  }
}

void LogCleanupFailure(const std::string &operation, const std::string &error) {
  LOG_ERROR << "brand rename cleanup failed during " << operation << ": "
            << error;
}

void ApplyUpdate(const drogon::HttpRequestPtr &req, const Callback &callback,
                 const std::string &old_name) {
  auto input = ParseUpdateRequest(req, callback);
  if (!input) {
    return;
  }

  const auto got_brands = assetsbo::storage::GetObject(kBrandsKey);
  if (got_brands.not_found || !got_brands.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Get failed",
              got_brands.not_found ? "brands.parquet not found in bucket"
                                   : got_brands.error);
    return;
  }
  auto parsed_brands = assetsbo::storage::ParseParquetTable(got_brands.body);
  if (!parsed_brands.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Parse failed",
              parsed_brands.error);
    return;
  }
  auto &table = parsed_brands.table;
  const auto name_idx = NameColumnIndex(table, callback);
  if (!name_idx) {
    return;
  }
  const auto row_idx = UniqueRowIndex(table, *name_idx, old_name, callback);
  if (!row_idx) {
    return;
  }

  const auto submitted_name = input->fields.find("name");
  const std::string new_name = submitted_name == input->fields.end()
                                   ? old_name
                                   : submitted_name->second;
  if (const auto reason = assetsbo::storage::RejectSegment(new_name, "name")) {
    SendError(callback, drogon::k400BadRequest, "Bad name", *reason);
    return;
  }
  const bool renamed = new_name != old_name;
  if (renamed) {
    for (std::size_t r = 0; r < table.rows.size(); ++r) {
      if (r != *row_idx && table.rows[r][*name_idx] == new_name) {
        SendError(callback, drogon::k409Conflict, "Name conflict",
                  "another brand is already named \"" + new_name + "\"");
        return;
      }
    }
  }

  storage::FieldOverrides scalar_fields;
  std::vector<storage::CellEdit> parquet_edits;
  for (const auto &[key, value] : input->fields) {
    const auto col = std::ranges::find(table.column_names, key);
    if (col == table.column_names.end()) {
      SendError(callback, drogon::k400BadRequest, "Bad field",
                "\"" + key + "\" is not a brand column");
      return;
    }
    const auto col_idx =
        static_cast<std::size_t>(col - table.column_names.begin());
    if (key == "name") {
      if (renamed) {
        parquet_edits.push_back({col_idx, value});
      }
    } else if (table.nested_columns[col_idx]) {
      parquet_edits.push_back({col_idx, value});
    } else {
      scalar_fields[key] = value;
    }
  }

  std::string new_brands_bytes;
  if (!parquet_edits.empty()) {
    const auto mutated = assetsbo::storage::ReplaceCells(
        got_brands.body, *row_idx, parquet_edits);
    if (!mutated.error.empty()) {
      SendError(callback, drogon::k400BadRequest, "Bad field", mutated.error);
      return;
    }
    new_brands_bytes = mutated.bytes;
  }

  storage::BrandOverrides original_overrides;
  storage::BrandOverrides transitional_overrides;
  storage::BrandOverrides final_overrides;
  bool write_overrides = renamed || !scalar_fields.empty();
  if (write_overrides) {
    auto fetched = FetchOverridesStrict(callback);
    if (!fetched) {
      return;
    }
    original_overrides = std::move(*fetched);

    storage::FieldOverrides merged_fields;
    if (const auto old = original_overrides.find(old_name);
        old != original_overrides.end()) {
      merged_fields = old->second;
    }
    merged_fields.erase("name");
    for (auto &[field, value] : scalar_fields) {
      merged_fields[field] = std::move(value);
    }

    if (renamed) {
      transitional_overrides = original_overrides;
      transitional_overrides[old_name] = merged_fields;
      transitional_overrides[new_name] = std::move(merged_fields);
      final_overrides = transitional_overrides;
      final_overrides.erase(old_name);
    } else {
      final_overrides = original_overrides;
      if (merged_fields.empty()) {
        final_overrides.erase(old_name);
      } else {
        final_overrides[old_name] = std::move(merged_fields);
      }
      write_overrides = final_overrides != original_overrides;
    }
  }

  std::vector<PendingImage> rename_images;
  if (renamed) {
    auto pending = PrepareRenameImages(old_name, new_name, input->images,
                                       callback);
    if (!pending) {
      return;
    }
    rename_images = std::move(*pending);
  }

  if (renamed) {
    std::vector<std::string> staged_keys;
    for (const auto &image : rename_images) {
      staged_keys.push_back(image.key);
      const auto put = assetsbo::storage::PutObject(image.key, image.body,
                                                    "image/png");
      if (!put.error.empty()) {
        RemoveStagedImages(staged_keys);
        SendError(callback, drogon::k502BadGateway, "Put failed", put.error);
        return;
      }
    }

    const auto put_transitional = assetsbo::storage::PutObject(
        kOverridesKey,
        assetsbo::storage::SerializeOverrides(transitional_overrides));
    if (!put_transitional.error.empty()) {
      RemoveStagedImages(staged_keys);
      SendError(callback, drogon::k502BadGateway, "Put failed",
                put_transitional.error);
      return;
    }

    const auto put_brands =
        assetsbo::storage::PutObject(kBrandsKey, new_brands_bytes);
    if (!put_brands.error.empty()) {
      RemoveStagedImages(staged_keys);
      SendError(callback, drogon::k502BadGateway, "Put failed",
                put_brands.error);
      return;
    }

    const auto put_final = assetsbo::storage::PutObject(
        kOverridesKey, assetsbo::storage::SerializeOverrides(final_overrides));
    if (!put_final.error.empty()) {
      LogCleanupFailure("override removal", put_final.error);
    }
    for (const auto kind : kImageKinds) {
      const auto removed =
          assetsbo::storage::DeleteObject(BrandImageKey(old_name, kind));
      if (!removed.error.empty()) {
        LogCleanupFailure("old image deletion", removed.error);
      }
    }
  } else {
    if (!parquet_edits.empty()) {
      const auto put =
          assetsbo::storage::PutObject(kBrandsKey, new_brands_bytes);
      if (!put.error.empty()) {
        SendError(callback, drogon::k502BadGateway, "Put failed", put.error);
        return;
      }
    }
    if (write_overrides) {
      const auto put = assetsbo::storage::PutObject(
          kOverridesKey,
          assetsbo::storage::SerializeOverrides(final_overrides));
      if (!put.error.empty()) {
        SendError(callback, drogon::k502BadGateway, "Put failed", put.error);
        return;
      }
    }
    for (const auto kind : kImageKinds) {
      const auto upload = input->images.find(std::string(kind));
      if (upload == input->images.end()) {
        continue;
      }
      const auto put = assetsbo::storage::PutObject(
          BrandImageKey(old_name, kind), upload->second, "image/png");
      if (!put.error.empty()) {
        SendError(callback, drogon::k502BadGateway, "Put failed", put.error);
        return;
      }
    }
  }

  callback(drogon::HttpResponse::newRedirectionResponse(
      "/v1/brand/" + EncodePathSegment(new_name) + "/details"));
}

} // namespace

void Brands::BrandsUpdate(const drogon::HttpRequestPtr &req, Callback &&callback,
                          std::string name) {
  if (const auto reason = assetsbo::storage::RejectSegment(name, "name")) {
    SendError(callback, drogon::k400BadRequest, "Bad name", *reason);
    return;
  }

  if (req->getMethod() == drogon::Get) {
    ShowEditForm(callback, name);
    return;
  }
  ApplyUpdate(req, callback, name);
}

} // namespace blackkeys::assetsbo::handling::brand
