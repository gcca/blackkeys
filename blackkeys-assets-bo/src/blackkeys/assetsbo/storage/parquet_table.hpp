#pragma once

#include <memory>
#include <string>
#include <vector>

#include <arrow/result.h>

namespace arrow {
class Table;
} // namespace arrow

namespace blackkeys::assetsbo::storage {

struct ParquetTable {
  std::vector<std::string> column_names;
  std::vector<bool> nested_columns;
  std::vector<std::vector<std::string>> rows;
};

struct ParquetOutcome {
  ParquetTable table;
  std::string error;
};

ParquetOutcome ParseParquetTable(const std::string &bytes);

// Shared by ParseParquetTable and storage::ReplaceCells: opens Parquet bytes
// already in memory into an Arrow table, with no column flattened or
// erased yet.
arrow::Result<std::shared_ptr<arrow::Table>> OpenParquetTable(const std::string &bytes);

} // namespace blackkeys::assetsbo::storage
