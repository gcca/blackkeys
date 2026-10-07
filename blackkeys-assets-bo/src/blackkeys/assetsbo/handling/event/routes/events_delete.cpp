#include "blackkeys/assetsbo/handling/event/routes/common.hpp"
namespace blackkeys::assetsbo::handling::event {
void Events::EventsDelete(const drogon::HttpRequestPtr &, Callback &&callback,
                          std::string title) {
  if (!ValidTitle(title, callback))
    return;
  auto snapshot = FetchSnapshot(callback);
  if (!snapshot)
    return;
  auto row = ResolveRow(*snapshot, title, callback);
  if (row)
    Save(storage::RemoveRow(snapshot->bytes, *row), "/v1/event/list", callback);
}
} // namespace blackkeys::assetsbo::handling::event
