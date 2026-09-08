#pragma once

#include <drogon/HttpController.h>

namespace blackkeys::assetsbo::handling::brand {

class Brands : public drogon::HttpController<Brands> {
public:
  METHOD_LIST_BEGIN
  ADD_METHOD_TO(Brands::BrandsList, "/v1/brand/list", drogon::Get);
  ADD_METHOD_TO(Brands::BrandsCreate, "/v1/brand/create", drogon::Get,
                drogon::Post);
  ADD_METHOD_TO(Brands::BrandsDetails, "/v1/brand/{name}/details", drogon::Get);
  ADD_METHOD_TO(Brands::BrandsImage, "/v1/brand/{name}/image/{kind}",
                drogon::Get);
  ADD_METHOD_TO(Brands::BrandsUpdate, "/v1/brand/{name}/update", drogon::Get,
                drogon::Post);
  ADD_METHOD_TO(Brands::BrandsDelete, "/v1/brand/{name}/delete", drogon::Post);
  METHOD_LIST_END

  void
  BrandsList(const drogon::HttpRequestPtr &req,
             std::function<void(const drogon::HttpResponsePtr &)> &&callback);

  void
  BrandsCreate(const drogon::HttpRequestPtr &req,
              std::function<void(const drogon::HttpResponsePtr &)> &&callback);

  void
  BrandsDetails(const drogon::HttpRequestPtr &req,
                std::function<void(const drogon::HttpResponsePtr &)> &&callback,
                std::string name);

  void
  BrandsImage(const drogon::HttpRequestPtr &req,
              std::function<void(const drogon::HttpResponsePtr &)> &&callback,
              std::string name, std::string kind);

  void
  BrandsUpdate(const drogon::HttpRequestPtr &req,
               std::function<void(const drogon::HttpResponsePtr &)> &&callback,
               std::string name);

  void
  BrandsDelete(const drogon::HttpRequestPtr &req,
               std::function<void(const drogon::HttpResponsePtr &)> &&callback,
               std::string name);
};

} // namespace blackkeys::assetsbo::handling::brand
