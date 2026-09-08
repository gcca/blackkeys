#pragma once

#include <string>

namespace blackkeys::assetsbo::core {

struct Endpoint {
  bool overridden = false;
  bool https = true;
  std::string host;
};

struct Settings {
  std::string access_key_id;
  std::string secret_access_key;
  std::string region;
  std::string bucket_name;
  Endpoint endpoint;
  std::string node_exporter_path;
};

struct SettingsResult {
  bool ok = false;
  Settings settings;
  std::string error;
};

SettingsResult LoadSettings();

} // namespace blackkeys::assetsbo::core
