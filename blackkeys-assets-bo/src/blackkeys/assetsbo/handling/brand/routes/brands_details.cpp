#include "blackkeys/assetsbo/handling/brand/routes.hpp"
#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include <utility>
#include <vector>

#include "blackkeys/assetsbo/storage/listing.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"

namespace blackkeys::assetsbo::handling::brand {

void Brands::BrandsDetails(const drogon::HttpRequestPtr &, Callback &&callback,
                           std::string name) {
  if (const auto reason = assetsbo::storage::RejectSegment(name, "name")) {
    SendError(callback, drogon::k400BadRequest, "Bad name", *reason);
    return;
  }

  auto found = FetchMatches(name, callback);
  if (!found) {
    return;
  }
  if (found->rows.empty()) {
    SendError(callback, drogon::k404NotFound, "Not found",
              "no brand named \"" + name + "\"");
    return;
  }

  std::vector<bool> marks;
  marks.reserve(found->column_names.size());
  for (const auto &column : found->column_names) {
    marks.push_back(IsOverridden(found->overrides, name, column));
  }
  std::vector<std::vector<bool>> overridden(found->rows.size(), marks);

  const auto &bucket = assetsbo::storage::BucketName();
  drogon::HttpViewData data;
  data.insert("title", std::string("Brands"));
  data.insert("heading", name);
  data.insert("meta", "s3://" + bucket + "/" + kBrandsKey);
  data.insert("columns", found->column_names);
  data.insert("nested_columns", found->nested_columns);
  data.insert("matches", found->rows);
  data.insert("overridden", overridden);
  data.insert("editable", found->rows.size() == 1);
  data.insert("image_uploads_enabled", false);
  SendView(callback, drogon::k200OK, "brands_details", std::move(data));
}

} // namespace blackkeys::assetsbo::handling::brand
