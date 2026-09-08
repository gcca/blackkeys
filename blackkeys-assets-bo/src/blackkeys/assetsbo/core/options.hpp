#pragma once

#include <charconv>
#include <cstdint>
#include <iostream>
#include <string>
#include <string_view>

namespace blackkeys::assetsbo::core {

struct Options {
  std::string bind = "::";
  std::uint16_t port = 8000;
};

inline void PrintUsage(std::ostream &out) {
  out << "blackkeys-assets-bo [--bind ADDRESS] [--port PORT]\n"
      << "Default bind :: (dual-stack) port 8000.\n"
      << "Reads AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION.\n"
      << "Optional AWS_ENDPOINT_URL_S3, BUCKET_NAME, and NODE_EXPORTER_PATH.\n";
}

inline bool FlagValue(std::string_view arg, std::string_view flag, int &index,
                      int argc, char **argv, std::string &value, bool &seen) {
  if (arg == flag) {
    seen = true;
    if (index + 1 >= argc) {
      return false;
    }
    value = argv[++index];
    return !value.empty();
  }
  const auto prefix = std::string(flag) + "=";
  if (arg.rfind(prefix, 0) == 0) {
    seen = true;
    value = std::string(arg.substr(prefix.size()));
    return !value.empty();
  }
  return false;
}

inline int InitOptions(int argc, char **argv, Options &options) {
  for (int index = 1; index < argc; ++index) {
    const std::string_view arg = argv[index];
    if (arg == "--help" || arg == "-h") {
      PrintUsage(std::cout);
      return 0;
    }

    bool seen = false;
    std::string value;
    if (FlagValue(arg, "--bind", index, argc, argv, value, seen) ||
        FlagValue(arg, "-b", index, argc, argv, value, seen)) {
      options.bind = std::move(value);
      continue;
    }
    if (seen) {
      PrintUsage(std::cerr);
      return 1;
    }

    if (FlagValue(arg, "--port", index, argc, argv, value, seen) ||
        FlagValue(arg, "-p", index, argc, argv, value, seen)) {
      unsigned int port = 0;
      const auto *begin = value.data();
      const auto *end = begin + value.size();
      const auto parsed = std::from_chars(begin, end, port);
      if (parsed.ec != std::errc{} || parsed.ptr != end || port < 1 ||
          port > 65535) {
        std::cerr << "port must be an integer from 1 to 65535\n";
        return 1;
      }
      options.port = static_cast<std::uint16_t>(port);
      continue;
    }
    if (seen) {
      PrintUsage(std::cerr);
      return 1;
    }

    PrintUsage(std::cerr);
    return 1;
  }
  return -1;
}

} // namespace blackkeys::assetsbo::core
