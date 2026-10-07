#include "blackkeys/assetsbo/storage/timestamp.hpp"

#include <chrono>
#include <iomanip>
#include <limits>
#include <regex>
#include <sstream>

namespace blackkeys::assetsbo::storage {
int TimestampDigits(arrow::TimeUnit::type unit) {
  switch (unit) {
  case arrow::TimeUnit::SECOND:
    return 0;
  case arrow::TimeUnit::MILLI:
    return 3;
  case arrow::TimeUnit::MICRO:
    return 6;
  default:
    return 9;
  }
}

arrow::Result<int64_t> ParseTimestamp(const std::string &text,
                                      arrow::TimeUnit::type unit) {
  static const std::regex pattern(
      R"(^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$)");
  std::smatch m;
  if (!std::regex_match(text, m, pattern))
    return arrow::Status::Invalid(
        "expected a timestamp with seconds and UTC offset");
  using namespace std::chrono;
  year_month_day date{year{std::stoi(m[1])},
                      month{static_cast<unsigned>(std::stoi(m[2]))},
                      day{static_cast<unsigned>(std::stoi(m[3]))}};
  int hour = std::stoi(m[4]), minute = std::stoi(m[5]),
      second = std::stoi(m[6]);
  if (!date.ok() || hour > 23 || minute > 59 || second > 59)
    return arrow::Status::Invalid("invalid calendar date or time");
  int offset = 0;
  std::string zone = m[8];
  if (zone != "Z") {
    int h = std::stoi(zone.substr(1, 2)), min = std::stoi(zone.substr(4, 2));
    if (h > 23 || min > 59)
      return arrow::Status::Invalid("invalid UTC offset");
    offset = (h * 60 + min) * 60 * (zone[0] == '+' ? 1 : -1);
  }
  int digits = TimestampDigits(unit);
  std::string fraction = m[7];
  if (fraction.size() > static_cast<std::size_t>(digits)) {
    if (fraction.find_first_not_of('0', digits) != std::string::npos)
      return arrow::Status::Invalid(
          "fraction exceeds stored timestamp precision");
    fraction.resize(digits);
  }
  fraction.append(digits - fraction.size(), '0');
  int64_t scale = 1;
  for (int i = 0; i < digits; ++i)
    scale *= 10;
  auto seconds =
      duration_cast<std::chrono::seconds>(sys_days{date}.time_since_epoch())
          .count() +
      hour * 3600 + minute * 60 + second - offset;
  __int128 value = static_cast<__int128>(seconds) * scale +
                   (fraction.empty() ? 0 : std::stoll(fraction));
  if (value < std::numeric_limits<int64_t>::min() ||
      value > std::numeric_limits<int64_t>::max())
    return arrow::Status::Invalid("timestamp out of range");
  return static_cast<int64_t>(value);
}

std::string LimaTimestamp(int64_t value, arrow::TimeUnit::type unit) {
  using namespace std::chrono;
  int digits = TimestampDigits(unit);
  int64_t scale = 1;
  for (int i = 0; i < digits; ++i)
    scale *= 10;
  int64_t seconds = value / scale, fraction = value % scale;
  if (fraction < 0) {
    --seconds;
    fraction += scale;
  }
  sys_seconds local{std::chrono::seconds{seconds - 5 * 3600}};
  auto days = floor<std::chrono::days>(local);
  year_month_day date{days};
  hh_mm_ss time{local - days};
  std::ostringstream out;
  out << std::setfill('0') << std::setw(4) << int(date.year()) << '-'
      << std::setw(2) << unsigned(date.month()) << '-' << std::setw(2)
      << unsigned(date.day()) << 'T' << std::setw(2) << time.hours().count()
      << ':' << std::setw(2) << time.minutes().count() << ':' << std::setw(2)
      << time.seconds().count();
  if (digits)
    out << '.' << std::setw(digits) << fraction;
  return out.str();
}
} // namespace blackkeys::assetsbo::storage
