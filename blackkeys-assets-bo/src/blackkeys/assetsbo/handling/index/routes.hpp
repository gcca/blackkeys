#pragma once

#include <drogon/HttpController.h>

namespace blackkeys::assetsbo::handling::index {

class Index : public drogon::HttpController<Index> {
public:
  METHOD_LIST_BEGIN
  ADD_METHOD_TO(Index::Home, "/", drogon::Get);
  ADD_METHOD_TO(Index::Healthcheck, "/healthcheck", drogon::Get);
  METHOD_LIST_END

  void
  Home(const drogon::HttpRequestPtr &req,
       std::function<void(const drogon::HttpResponsePtr &)> &&callback);

  void
  Healthcheck(const drogon::HttpRequestPtr &req,
              std::function<void(const drogon::HttpResponsePtr &)> &&callback);
};

} // namespace blackkeys::assetsbo::handling::index
