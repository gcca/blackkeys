#pragma once

#include <optional>
#include <string>

#include "blackkeys/assetsbo/core/settings.hpp"

namespace blackkeys::assetsbo::storage {

struct GetOutcome {
  std::string body;
  bool not_found = false;
  std::string error;
  std::optional<std::string> last_modified;
};

struct PutOutcome {
  std::string error;
};

struct DeleteOutcome {
  std::string error;
};

class ObjectStore {
public:
  virtual ~ObjectStore() = default;
  virtual GetOutcome Get(const std::string &key) = 0;
  virtual PutOutcome Put(const std::string &key, const std::string &body,
                         const std::string &content_type) = 0;
  virtual DeleteOutcome Delete(const std::string &key) = 0;
};

void InitClient(const assetsbo::core::Settings &settings);
const std::string &BucketName();
GetOutcome GetObject(const std::string &key);
PutOutcome PutObject(const std::string &key, const std::string &body,
                     const std::string &content_type = "application/json");
DeleteOutcome DeleteObject(const std::string &key);

void SetObjectStoreForTesting(ObjectStore *store);

} // namespace blackkeys::assetsbo::storage
