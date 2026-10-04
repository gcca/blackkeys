#include "blackkeys/assetsbo/handling/brand/routes.hpp"
#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include "blackkeys/assetsbo/storage/listing.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"

namespace blackkeys::assetsbo::handling::brand {

void Brands::BrandsImage(const drogon::HttpRequestPtr &, Callback &&callback,
                         std::string name, std::string kind) {
  if (const auto reason = assetsbo::storage::RejectSegment(name, "name")) {
    SendError(callback, drogon::k400BadRequest, "Bad name", *reason);
    return;
  }
  if (!IsImageKind(kind)) {
    SendError(callback, drogon::k400BadRequest, "Bad image",
              "image kind must be \"logo\" or \"picture\"");
    return;
  }

  const auto got = assetsbo::storage::GetObject(BrandImageKey(name, kind));
  if (got.not_found) {
    SendError(callback, drogon::k404NotFound, "Image not found",
              kind + ".webp is not available for this brand");
    return;
  }
  if (!got.error.empty()) {
    SendError(callback, drogon::k502BadGateway, "Get failed", got.error);
    return;
  }

  auto response = drogon::HttpResponse::newHttpResponse();
  response->setStatusCode(drogon::k200OK);
  response->setContentTypeString(kImageContentType);
  response->addHeader("Cache-Control", "no-store");
  response->addHeader("Content-Length", std::to_string(got.body.size()));
  if (got.last_modified) {
    response->addHeader("Last-Modified", *got.last_modified);
  }
  response->setBody(got.body);
  callback(response);
}

} // namespace blackkeys::assetsbo::handling::brand
