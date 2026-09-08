#include <cstdlib>
#include <cstddef>
#include <iostream>
#include <string>

#include <aws/core/Aws.h>
#include <drogon/drogon.h>
#include <trantor/utils/Logger.h>

#include "blackkeys/assetsbo/core/node_exporter.hpp"
#include "blackkeys/assetsbo/core/options.hpp"
#include "blackkeys/assetsbo/core/settings.hpp"
#include "blackkeys/assetsbo/storage/s3.hpp"

namespace {

struct AwsApi {
  Aws::SDKOptions options;
  AwsApi() { Aws::InitAPI(options); }
  ~AwsApi() { Aws::ShutdownAPI(options); }
};

std::string EndpointLabel(const blackkeys::assetsbo::core::Endpoint &endpoint) {
  if (!endpoint.overridden) {
    return "default";
  }
  return std::string(endpoint.https ? "https://" : "http://") + endpoint.host;
}

} // namespace

int main(int argc, char **argv) {
  blackkeys::assetsbo::core::Options options;
  const int parsed = blackkeys::assetsbo::core::InitOptions(argc, argv, options);
  if (parsed >= 0) {
    return parsed;
  }

  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  if (!loaded.ok) {
    std::cerr << loaded.error << "\n";
    return EXIT_FAILURE;
  }

  AwsApi aws_api;
  blackkeys::assetsbo::storage::InitClient(loaded.settings);
  blackkeys::assetsbo::core::StartNodeExporter(loaded.settings.node_exporter_path);

  LOG_INFO << "blackkeys-assets-bo: starting"
           << " bucket=" << loaded.settings.bucket_name
           << " endpoint=" << EndpointLabel(loaded.settings.endpoint)
           << " bind=" << options.bind << " port=" << options.port;

  constexpr std::size_t kMaxRequestBodyBytes = 22U * 1024U * 1024U;
  drogon::app()
      .setClientMaxBodySize(kMaxRequestBodyBytes)
      .setClientMaxMemoryBodySize(kMaxRequestBodyBytes)
      .addListener(options.bind, options.port)
      .run();
  return EXIT_SUCCESS;
}
