#include "blackkeys/assetsbo/storage/listing.hpp"

namespace blackkeys::assetsbo::storage {

std::optional<std::string> RejectSegment(std::string_view value,
                                         std::string_view label) {
  if (value.empty()) {
    return std::string(label) + " is empty";
  }
  if (value == "." || value == "..") {
    return std::string(label) + " is not allowed";
  }
  for (const unsigned char ch : value) {
    if (ch < 0x20 || ch == 0x7f) {
      return std::string(label) + " contains a control character";
    }
    if (ch == '/' || ch == '\\') {
      return std::string(label) + " must be one path segment";
    }
  }
  return std::nullopt;
}

} // namespace blackkeys::assetsbo::storage
