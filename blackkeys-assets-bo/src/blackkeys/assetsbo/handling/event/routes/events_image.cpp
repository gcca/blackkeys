#include <arrow/scalar.h>

#include "blackkeys/assetsbo/handling/event/routes/common.hpp"
namespace blackkeys::assetsbo::handling::event {
void Events::EventsImage(const drogon::HttpRequestPtr &, Callback &&callback,
                         std::string title) {
  if (!ValidTitle(title, callback))
    return;
  auto snapshot = FetchSnapshot(callback);
  if (!snapshot)
    return;
  auto row = ResolveRow(*snapshot, title, callback);
  if (!row)
    return;
  auto scalar = snapshot->arrow->column(snapshot->image)->GetScalar(*row);
  if (!scalar.ok()) {
    SendError(callback, drogon::k502BadGateway, scalar.status().ToString());
    return;
  }
  if (!(*scalar)->is_valid) {
    SendError(callback, drogon::k404NotFound, "image not uploaded");
    return;
  }
  auto bytes = std::static_pointer_cast<arrow::BaseBinaryScalar>(*scalar)
                   ->value->ToString();
  auto response = drogon::HttpResponse::newHttpResponse();
  response->setContentTypeString("image/webp");
  response->addHeader("Cache-Control", "no-store");
  response->addHeader("Content-Length", std::to_string(bytes.size()));
  response->setBody(std::move(bytes));
  callback(response);
}
} // namespace blackkeys::assetsbo::handling::event
