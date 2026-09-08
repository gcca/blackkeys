#pragma once

#include <string>

namespace blackkeys::assetsbo::core {

// Spawns node_exporter (listening on :9100) as a detached child process. A
// no-op if path is empty. A spawn failure is logged as a warning, not fatal:
// this service's /metrics endpoint is not wired into any scrape config yet,
// so the web app itself must not go down over the exporter failing to start.
void StartNodeExporter(const std::string &path);

} // namespace blackkeys::assetsbo::core
