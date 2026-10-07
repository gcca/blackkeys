#pragma once
#include <optional>

#include <arrow/table.h>

#include "blackkeys/assetsbo/handling/event/routes.hpp"
#include "blackkeys/assetsbo/storage/parquet_mutation.hpp"
#include "blackkeys/assetsbo/storage/parquet_table.hpp"

namespace blackkeys::assetsbo::handling::event {
using Callback = Events::Callback;
inline constexpr char kEventsKey[] = "events.parquet";
inline constexpr std::size_t kMaxImageBytes = 20U * 1024U * 1024U;
struct Snapshot {
  std::string bytes;
  storage::ParquetTable display;
  std::shared_ptr<arrow::Table> arrow;
  int title, start, end, image;
};
std::string EventPath(const std::string &title, const std::string &suffix);
void SendError(const Callback &, drogon::HttpStatusCode,
               const std::string &message);
bool ValidTitle(const std::string &, const Callback &);
std::optional<Snapshot> FetchSnapshot(const Callback &);
std::optional<std::size_t> ResolveRow(const Snapshot &, const std::string &,
                                      const Callback &);
void ShowRow(const Snapshot &, std::size_t, const std::string &view,
             const Callback &);
void ShowCreate(const Snapshot &, const Callback &);
void Mutate(const drogon::HttpRequestPtr &, const Callback &, const Snapshot &,
            std::optional<std::size_t>);
void Save(const storage::MutationOutcome &, const std::string &redirect,
          const Callback &);
} // namespace blackkeys::assetsbo::handling::event
