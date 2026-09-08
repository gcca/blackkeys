#pragma once

#include <optional>
#include <string>
#include <string_view>

namespace blackkeys::assetsbo::storage {

std::optional<std::string> RejectSegment(std::string_view value,
                                         std::string_view label);

} // namespace blackkeys::assetsbo::storage
