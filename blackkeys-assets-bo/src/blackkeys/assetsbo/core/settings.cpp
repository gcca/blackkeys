#include "blackkeys/assetsbo/core/settings.hpp"

#include <cstdlib>
#include <optional>
#include <string_view>

namespace blackkeys::assetsbo::core {
namespace {

constexpr std::string_view kBucketDefault = "blackkeys-assets";

std::string ReadEnv(const char *name) {
  const char *value = std::getenv(name);
  return value == nullptr ? std::string{} : std::string{value};
}

std::optional<std::string> RequireEnv(const char *name, std::string &error) {
  auto value = ReadEnv(name);
  if (value.empty()) {
    error = std::string(name) + " must not be empty";
    return std::nullopt;
  }
  return value;
}

bool ParseEndpoint(std::string_view url, Endpoint &endpoint,
                   std::string &error) {
  if (url.empty()) {
    endpoint = {};
    return true;
  }

  const auto scheme_end = url.find("://");
  if (scheme_end == std::string_view::npos) {
    error = "AWS_ENDPOINT_URL_S3 must include http:// or https://";
    return false;
  }

  const auto scheme = url.substr(0, scheme_end);
  if (scheme == "https") {
    endpoint.https = true;
  } else if (scheme == "http") {
    endpoint.https = false;
  } else {
    error = "AWS_ENDPOINT_URL_S3 must use http or https";
    return false;
  }

  auto rest = url.substr(scheme_end + 3);
  if (rest.empty() || rest.find('@') != std::string_view::npos) {
    error = "AWS_ENDPOINT_URL_S3 must be a host without user info";
    return false;
  }

  const auto slash = rest.find('/');
  if (slash != std::string_view::npos) {
    const auto path = rest.substr(slash);
    if (path != "/") {
      error = "AWS_ENDPOINT_URL_S3 must not include a path";
      return false;
    }
    rest = rest.substr(0, slash);
  }
  if (rest.empty()) {
    error = "AWS_ENDPOINT_URL_S3 must include a host";
    return false;
  }

  endpoint.overridden = true;
  endpoint.host = std::string(rest);
  return true;
}

} // namespace

SettingsResult LoadSettings() {
  SettingsResult result;
  auto access_key = RequireEnv("AWS_ACCESS_KEY_ID", result.error);
  if (!access_key) {
    return result;
  }
  auto secret_key = RequireEnv("AWS_SECRET_ACCESS_KEY", result.error);
  if (!secret_key) {
    return result;
  }
  auto region = RequireEnv("AWS_REGION", result.error);
  if (!region) {
    return result;
  }
  if (!ParseEndpoint(ReadEnv("AWS_ENDPOINT_URL_S3"), result.settings.endpoint,
                     result.error)) {
    return result;
  }

  auto bucket = ReadEnv("BUCKET_NAME");
  if (bucket.empty()) {
    bucket = std::string(kBucketDefault);
  }

  result.settings.access_key_id = std::move(*access_key);
  result.settings.secret_access_key = std::move(*secret_key);
  result.settings.region = std::move(*region);
  result.settings.bucket_name = std::move(bucket);
  result.settings.node_exporter_path = ReadEnv("NODE_EXPORTER_PATH");
  result.ok = true;
  result.error.clear();
  return result;
}

} // namespace blackkeys::assetsbo::core
