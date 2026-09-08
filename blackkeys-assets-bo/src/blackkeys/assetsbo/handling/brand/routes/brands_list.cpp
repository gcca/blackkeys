#include "blackkeys/assetsbo/handling/brand/routes.hpp"
#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include <utility>
#include <vector>

#include "blackkeys/assetsbo/storage/s3.hpp"

namespace blackkeys::assetsbo::handling::brand {

void Brands::BrandsList(const drogon::HttpRequestPtr &, Callback &&callback) {
  auto table = FetchBrandsTable(callback);
  if (!table) {
    return;
  }
  const auto name_idx = NameColumnIndex(*table, callback);
  if (!name_idx) {
    return;
  }
  ApplyOverrides(*table, FetchOverrides(), *name_idx);

  std::vector<std::string> names;
  names.reserve(table->rows.size());
  for (const auto &row : table->rows) {
    names.push_back(row[*name_idx]);
  }

  const auto &bucket = assetsbo::storage::BucketName();
  drogon::HttpViewData data;
  data.insert("title", std::string("Brands"));
  data.insert("heading", std::string("Brands"));
  data.insert("meta", "s3://" + bucket + "/" + kBrandsKey);
  data.insert("names", names);
  SendView(callback, drogon::k200OK, "brands_list", std::move(data));
}

} // namespace blackkeys::assetsbo::handling::brand
