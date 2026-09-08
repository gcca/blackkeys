#include "blackkeys/assetsbo/core/node_exporter.hpp"

#include <spawn.h>

#include <array>
#include <cstring>

#include <trantor/utils/Logger.h>

extern char **environ;

namespace blackkeys::assetsbo::core {

void StartNodeExporter(const std::string &path) {
  if (path.empty()) {
    return;
  }

  static constexpr char kListenFlag[] = "--web.listen-address=:9100";
  static constexpr char kNoKernelHungFlag[] = "--no-collector.kernel_hung";
  std::array<char *, 4> argv{const_cast<char *>(path.c_str()),
                             const_cast<char *>(kListenFlag),
                             const_cast<char *>(kNoKernelHungFlag),
                             nullptr};

  pid_t pid = 0;
  const int rc = posix_spawn(&pid, path.c_str(), nullptr, nullptr,
                             argv.data(), environ);
  if (rc != 0) {
    LOG_WARN << "node_exporter: spawn failed for " << path << ": "
             << std::strerror(rc);
    return;
  }
  LOG_INFO << "node_exporter: started pid=" << pid << " path=" << path;
}

} // namespace blackkeys::assetsbo::core
