#pragma once

#include <drogon/HttpResponse.h>

#include <cstddef>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "blackkeys/assetsbo/storage/overrides.hpp"
#include "blackkeys/assetsbo/storage/parquet_table.hpp"

namespace blackkeys::assetsbo::handling::brand {

using Callback = std::function<void(const drogon::HttpResponsePtr &)>;

inline constexpr const char *kBrandsKey = "brands.parquet";
inline constexpr const char *kOverridesKey = "brand-overrides.json";
inline constexpr std::size_t kMaxPngBytes = 10U * 1024U * 1024U;

bool IsImageKind(std::string_view kind);
std::string BrandImageKey(const std::string &name, std::string_view kind);
std::string EncodePathSegment(const std::string &value);
std::optional<std::string> ValidatePngUpload(std::string_view bytes);

void SendView(const Callback &callback, drogon::HttpStatusCode status,
              const std::string &view, drogon::HttpViewData data);

void SendError(const Callback &callback, drogon::HttpStatusCode status,
               const std::string &heading, const std::string &message);

std::optional<storage::ParquetTable> FetchBrandsTable(const Callback &callback);

std::optional<std::size_t> NameColumnIndex(const storage::ParquetTable &table,
                                           const Callback &callback);

// Locates the single row where table.rows[r][name_idx] == name. Self-reports
// its own error like NameColumnIndex: 404 if no row matches, 409 if more than
// one does (a row-position-targeted edit, unlike a name-keyed overlay merge,
// cannot disambiguate which row to target).
std::optional<std::size_t> UniqueRowIndex(const storage::ParquetTable &table,
                                          std::size_t name_idx, const std::string &name,
                                          const Callback &callback);

storage::BrandOverrides FetchOverrides();

void ApplyOverrides(storage::ParquetTable &table,
                    const storage::BrandOverrides &overrides,
                    std::size_t name_idx);

bool IsOverridden(const storage::BrandOverrides &overrides,
                  const std::string &name, const std::string &field);

// Renders a nested (struct/list<struct>) cell's JSON text (as produced by
// storage::RenderScalar) as an HTML table for the details page. Falls back to
// escaped preformatted text if json_text does not parse as JSON.
std::string RenderNestedCellHtml(const std::string &json_text);

struct BrandMatches {
  std::vector<std::string> column_names;
  std::vector<bool> nested_columns;
  std::vector<std::vector<std::string>> rows;
  storage::BrandOverrides overrides;
};

std::optional<BrandMatches> FetchMatches(const std::string &name,
                                         const Callback &callback);

} // namespace blackkeys::assetsbo::handling::brand
