#pragma once
#include <cstdint>
#include <string>

#include <arrow/result.h>
#include <arrow/type.h>

namespace blackkeys::assetsbo::storage {
int TimestampDigits(arrow::TimeUnit::type unit);
arrow::Result<int64_t> ParseTimestamp(const std::string &text,
                                      arrow::TimeUnit::type unit);
std::string LimaTimestamp(int64_t value, arrow::TimeUnit::type unit);
} // namespace blackkeys::assetsbo::storage
