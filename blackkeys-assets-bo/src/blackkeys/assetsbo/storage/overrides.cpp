#include "blackkeys/assetsbo/storage/overrides.hpp"

#include <memory>
#include <sstream>

#include <json/json.h>

namespace blackkeys::assetsbo::storage {

OverridesOutcome ParseOverrides(const std::string &bytes) {
  OverridesOutcome outcome;

  if (bytes.find_first_not_of(" \t\r\n") == std::string::npos) {
    return outcome;
  }

  Json::Value root;
  Json::CharReaderBuilder builder;
  std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
  std::string errors;
  if (!reader->parse(bytes.data(), bytes.data() + bytes.size(), &root,
                     &errors)) {
    outcome.error = errors.empty() ? "invalid overrides JSON" : errors;
    return outcome;
  }

  if (!root.isObject()) {
    outcome.error = "overrides JSON root is not an object";
    return outcome;
  }

  for (const auto &name : root.getMemberNames()) {
    const auto &fields = root[name];
    if (!fields.isObject()) {
      continue;
    }
    FieldOverrides field_overrides;
    for (const auto &field : fields.getMemberNames()) {
      const auto &value = fields[field];
      if (value.isString()) {
        field_overrides[field] = value.asString();
      }
    }
    outcome.overrides[name] = std::move(field_overrides);
  }
  return outcome;
}

std::string SerializeOverrides(const BrandOverrides &overrides) {
  Json::Value root(Json::objectValue);
  for (const auto &[name, fields] : overrides) {
    Json::Value entry(Json::objectValue);
    for (const auto &[field, value] : fields) {
      entry[field] = value;
    }
    root[name] = entry;
  }

  Json::StreamWriterBuilder builder;
  builder["indentation"] = "";
  return Json::writeString(builder, root);
}

} // namespace blackkeys::assetsbo::storage
