#pragma once

#include <string>
#include <unordered_map>

namespace blackkeys::assetsbo::storage {

using FieldOverrides = std::unordered_map<std::string, std::string>;
using BrandOverrides = std::unordered_map<std::string, FieldOverrides>;

struct OverridesOutcome {
  BrandOverrides overrides;
  std::string error;
};

OverridesOutcome ParseOverrides(const std::string &bytes);
std::string SerializeOverrides(const BrandOverrides &overrides);

} // namespace blackkeys::assetsbo::storage
