#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace blackkeys::assetsbo::storage {

struct CellEdit {
  std::size_t column_index;
  std::string text; // JSON for nested columns, plain text otherwise
  // Raw binary bytes (including NULs); empty bytes are distinct from null.
  std::optional<std::string> binary = std::nullopt;
};

struct MutationOutcome {
  std::string bytes;
  std::string error;
};

// Rebuilds `parquet_bytes` with each `edits[i].column_index` cell of
// `row_index` replaced by the value parsed from `edits[i].text`, and every
// other cell left untouched. Struct/list cells use JSON; scalar
// BOOL/INT32/INT64/STRING cells use their rendered plain-text form;
// TIMESTAMP uses timestamp text with an explicit UTC offset. Binary cells
// use `binary`; absent binary plus blank text clears the cell. A MAP,
// unsupported scalar type, or out-of-range index is rejected with a
// descriptive error, `bytes` empty. Pure and self-contained: no S3/Drogon
// dependency.
MutationOutcome ReplaceCells(const std::string &parquet_bytes,
                             std::size_t row_index,
                             const std::vector<CellEdit> &edits);

struct NewCell {
  std::size_t column_index;
  std::string text; // JSON for nested columns, plain text otherwise
  // Raw binary bytes (including NULs); empty bytes are distinct from null.
  std::optional<std::string> binary = std::nullopt;
};

// Appends one new row to the end of `parquet_bytes`, growing row count by
// exactly one. A column with no entry in `cells` (or a blank/whitespace-only
// `text`) gets a null cell. A struct/list<struct> column's `text` is parsed
// as JSON, same contract as ReplaceCells's `CellEdit::text`. Any other
// column's `text` is parsed according to its Arrow type
// (BOOL/INT32/INT64/STRING/TIMESTAMP); any other column type given a non-blank
// value, or an out-of-range `column_index`, is rejected with a descriptive
// error, `bytes` empty. Pure and self-contained: no S3/Drogon dependency.
MutationOutcome AppendRow(const std::string &parquet_bytes,
                          const std::vector<NewCell> &cells);

// Rebuilds `parquet_bytes` with `row_index` removed entirely, shrinking row
// count by exactly one. Every other row is left untouched, in order. An
// out-of-range `row_index` is rejected with a descriptive error, `bytes`
// empty. Pure and self-contained: no S3/Drogon dependency.
MutationOutcome RemoveRow(const std::string &parquet_bytes,
                          std::size_t row_index);

} // namespace blackkeys::assetsbo::storage
