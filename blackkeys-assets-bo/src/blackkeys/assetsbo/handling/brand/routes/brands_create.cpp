#include "blackkeys/assetsbo/handling/brand/routes.hpp"
#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include <algorithm>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "blackkeys/assetsbo/storage/listing.hpp"
#include "blackkeys/assetsbo/storage/parquet_mutation.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"

namespace blackkeys::assetsbo::handling::brand {
namespace {

void ShowCreateForm(const Callback &callback) {
  auto table = FetchBrandsTable(callback);
  if (!table) {
    return;
  }

  const auto &bucket = assetsbo::storage::BucketName();
  drogon::HttpViewData data;
  data.insert("title", std::string("Brands"));
  data.insert("heading", std::string("Create brand"));
  data.insert("meta", "s3://" + bucket + "/" + kBrandsKey);
  data.insert("columns", table->column_names);
  data.insert("nested_columns", table->nested_columns);
  data.insert("row", std::vector<std::string>(table->column_names.size()));
  SendView(callback, drogon::k200OK, "brands_create", std::move(data));
}

// Every check below, and every S3-dependent branch after it, is not exercised
// by handling/brand/routes-test.cc: it always calls FetchBrandsTable first,
// which fails immediately with "S3Error" whenever no live S3 client is
// initialized -- always true in that test binary. Same accepted gap as
// BrandsUpdate::ApplyUpdate. Real coverage of the JSON/scalar<->Arrow
// conversion this depends on lives in storage/parquet_mutation-test.cc,
// which needs no S3 at all.
void ApplyCreate(const drogon::HttpRequestPtr &req, const Callback &callback) {
  auto table = FetchBrandsTable(callback);
  if (!table) {
    return;
  }
  const auto name_idx = NameColumnIndex(*table, callback);
  if (!name_idx) {
    return;
  }

  std::vector<storage::NewCell> cells;
  std::optional<std::string> name;
  for (const auto &[key, value] : req->getParameters()) {
    const auto col = std::ranges::find(table->column_names, key);
    if (col == table->column_names.end()) {
      SendError(callback, drogon::k400BadRequest, "Bad field",
               "\"" + key + "\" is not a brand column");
      return;
    }
    const auto col_idx = static_cast<std::size_t>(col - table->column_names.begin());
    if (col_idx == *name_idx) {
      name = value;
    }
    cells.push_back({col_idx, value});
  }

  if (!name || name->empty()) {
    SendError(callback, drogon::k400BadRequest, "Bad name", "a brand name is required");
    return;
  }
  if (const auto reason = assetsbo::storage::RejectSegment(*name, "name")) {
    SendError(callback, drogon::k400BadRequest, "Bad name", *reason);
    return;
  }
  for (const auto &row : table->rows) {
    if (row[*name_idx] == *name) {
      SendError(callback, drogon::k409Conflict, "Cannot create",
               "a brand named \"" + *name + "\" already exists");
      return;
    }
  }

  const auto got = assetsbo::storage::GetObject(kBrandsKey);
  if (got.not_found || !got.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Get failed",
             got.not_found ? "brands.parquet not found in bucket" : got.error);
    return;
  }
  const auto mutated = assetsbo::storage::AppendRow(got.body, cells);
  if (!mutated.error.empty()) {
    SendError(callback, drogon::k400BadRequest, "Bad field", mutated.error);
    return;
  }

  const auto put = assetsbo::storage::PutObject(kBrandsKey, mutated.bytes);
  if (!put.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Put failed", put.error);
    return;
  }

  callback(drogon::HttpResponse::newRedirectionResponse(
      "/v1/brand/" + EncodePathSegment(*name) + "/details"));
}

} // namespace

void Brands::BrandsCreate(const drogon::HttpRequestPtr &req, Callback &&callback) {
  if (req->getMethod() == drogon::Get) {
    ShowCreateForm(callback);
    return;
  }
  ApplyCreate(req, callback);
}

} // namespace blackkeys::assetsbo::handling::brand
