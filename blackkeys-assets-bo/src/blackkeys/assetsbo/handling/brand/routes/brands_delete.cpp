#include "blackkeys/assetsbo/handling/brand/routes.hpp"
#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include "blackkeys/assetsbo/storage/listing.hpp"
#include "blackkeys/assetsbo/storage/parquet_mutation.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"

namespace blackkeys::assetsbo::handling::brand {
namespace {

// Same accepted gap as ApplyUpdate/ApplyCreate: every S3-dependent branch
// below is not exercised by handling/brand/routes-test.cc, since
// FetchBrandsTable always fails immediately with "S3Error" whenever no live
// S3 client is initialized -- always true in that test binary. Real coverage
// of the Arrow row-removal logic this depends on lives in
// storage/parquet_mutation-test.cc, which needs no S3 at all.
void ApplyDelete(const Callback &callback, const std::string &name) {
  auto table = FetchBrandsTable(callback);
  if (!table) {
    return;
  }
  const auto name_idx = NameColumnIndex(*table, callback);
  if (!name_idx) {
    return;
  }
  const auto row_idx = UniqueRowIndex(*table, *name_idx, name, callback);
  if (!row_idx) {
    return;
  }

  const auto got = assetsbo::storage::GetObject(kBrandsKey);
  if (got.not_found || !got.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Get failed",
             got.not_found ? "brands.parquet not found in bucket" : got.error);
    return;
  }
  const auto mutated = assetsbo::storage::RemoveRow(got.body, *row_idx);
  if (!mutated.error.empty()) {
    SendError(callback, drogon::k400BadRequest, "Bad row", mutated.error);
    return;
  }

  // The parquet rewrite is the higher-risk, harder-to-redo write, so it goes
  // first: if it fails, the overlay (still holding the prior, known-good
  // state) is never touched.
  const auto put = assetsbo::storage::PutObject(kBrandsKey, mutated.bytes);
  if (!put.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Put failed", put.error);
    return;
  }

  const auto got_overrides = assetsbo::storage::GetObject(kOverridesKey);
  if (!got_overrides.not_found) {
    if (!got_overrides.error.empty()) {
      SendError(callback, drogon::k502BadGateway, "Get failed", got_overrides.error);
      return;
    }
    auto parsed = assetsbo::storage::ParseOverrides(got_overrides.body);
    if (!parsed.error.empty()) {
      SendError(callback, drogon::k502BadGateway, "Parse failed", parsed.error);
      return;
    }
    if (parsed.overrides.contains(name)) {
      parsed.overrides.erase(name);
      const auto new_overrides_bytes =
          assetsbo::storage::SerializeOverrides(parsed.overrides);
      const auto put_overrides =
          assetsbo::storage::PutObject(kOverridesKey, new_overrides_bytes);
      if (!put_overrides.error.empty()) {
        SendError(callback, drogon::k502BadGateway, "Put failed", put_overrides.error);
        return;
      }
    }
  }

  callback(drogon::HttpResponse::newRedirectionResponse("/v1/brand/list"));
}

} // namespace

void Brands::BrandsDelete(const drogon::HttpRequestPtr &req, Callback &&callback,
                          std::string name) {
  if (const auto reason = assetsbo::storage::RejectSegment(name, "name")) {
    SendError(callback, drogon::k400BadRequest, "Bad name", *reason);
    return;
  }
  ApplyDelete(callback, name);
}

} // namespace blackkeys::assetsbo::handling::brand
