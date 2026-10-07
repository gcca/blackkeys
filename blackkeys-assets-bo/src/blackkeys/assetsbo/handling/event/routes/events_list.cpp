#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"
#include "blackkeys/assetsbo/handling/event/routes/common.hpp"
namespace blackkeys::assetsbo::handling::event {
void Events::EventsList(const drogon::HttpRequestPtr &, Callback &&callback) {
  auto snapshot = FetchSnapshot(callback);
  if (!snapshot)
    return;
  drogon::HttpViewData data;
  data.insert("title", std::string("Events"));
  data.insert("heading", std::string("Events"));
  data.insert("meta", std::string("America/Lima (UTC−05:00)"));
  std::vector<std::vector<std::string>> rows;
  for (const auto &row : snapshot->display.rows)
    rows.push_back(
        {row[snapshot->title], row[snapshot->start], row[snapshot->end]});
  data.insert("rows", rows);
  brand::SendView(callback, drogon::k200OK, "events_list", std::move(data));
}
} // namespace blackkeys::assetsbo::handling::event
