#include "blackkeys/assetsbo/handling/event/routes/common.hpp"
namespace blackkeys::assetsbo::handling::event {
void Events::EventsCreate(const drogon::HttpRequestPtr &req,
                          Callback &&callback) {
  auto snapshot = FetchSnapshot(callback);
  if (!snapshot)
    return;
  if (req->getMethod() == drogon::Get)
    ShowCreate(*snapshot, callback);
  else
    Mutate(req, callback, *snapshot, std::nullopt);
}
} // namespace blackkeys::assetsbo::handling::event
