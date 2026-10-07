#include "blackkeys/assetsbo/handling/event/routes/common.hpp"
namespace blackkeys::assetsbo::handling::event {
void Events::EventsUpdate(const drogon::HttpRequestPtr &req,
                          Callback &&callback, std::string title) {
  if (!ValidTitle(title, callback))
    return;
  auto snapshot = FetchSnapshot(callback);
  if (!snapshot)
    return;
  auto row = ResolveRow(*snapshot, title, callback);
  if (!row)
    return;
  if (req->getMethod() == drogon::Get)
    ShowRow(*snapshot, *row, "events_edit", callback);
  else
    Mutate(req, callback, *snapshot, *row);
}
} // namespace blackkeys::assetsbo::handling::event
