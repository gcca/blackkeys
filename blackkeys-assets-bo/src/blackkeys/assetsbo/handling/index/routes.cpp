#include "blackkeys/assetsbo/handling/index/routes.hpp"

namespace blackkeys::assetsbo::handling::index {

void Index::Home(const drogon::HttpRequestPtr &,
                 std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
  drogon::HttpViewData data;
  data.insert("title", std::string("Backoffice"));
  data.insert("heading", std::string("Backoffice"));
  data.insert("meta", std::string{});
  callback(drogon::HttpResponse::newHttpViewResponse("home", data));
}

void Index::Healthcheck(
    const drogon::HttpRequestPtr &,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
  auto response = drogon::HttpResponse::newHttpResponse();
  response->setContentTypeCode(drogon::CT_TEXT_PLAIN);
  response->setBody("🍻");
  callback(response);
}

} // namespace blackkeys::assetsbo::handling::index
