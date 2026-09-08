#include "blackkeys/assetsbo/storage/parquet_table.hpp"

#include <memory>
#include <utility>

#include <arrow/chunked_array.h>
#include <arrow/io/memory.h>
#include <arrow/result.h>
#include <arrow/scalar.h>
#include <arrow/status.h>
#include <arrow/table.h>
#include <arrow/type.h>
#include <json/json.h>
#include <parquet/arrow/reader.h>

namespace blackkeys::assetsbo::storage {
namespace {

bool IsNestedTypeId(arrow::Type::type id) {
  switch (id) {
  case arrow::Type::STRUCT:
  case arrow::Type::LIST:
  case arrow::Type::LARGE_LIST:
  case arrow::Type::FIXED_SIZE_LIST:
  case arrow::Type::MAP:
    return true;
  default:
    return false;
  }
}

Json::Value ScalarToJson(const std::shared_ptr<arrow::Scalar> &cell) {
  if (!cell->is_valid) {
    return Json::Value(Json::nullValue);
  }
  switch (cell->type->id()) {
  case arrow::Type::BOOL:
    return Json::Value(std::static_pointer_cast<arrow::BooleanScalar>(cell)->value);
  case arrow::Type::INT32:
    return Json::Value(std::static_pointer_cast<arrow::Int32Scalar>(cell)->value);
  case arrow::Type::INT64:
    return Json::Value(static_cast<Json::Int64>(
        std::static_pointer_cast<arrow::Int64Scalar>(cell)->value));
  case arrow::Type::STRING:
    return Json::Value(
        std::static_pointer_cast<arrow::StringScalar>(cell)->value->ToString());
  case arrow::Type::STRUCT: {
    auto s = std::static_pointer_cast<arrow::StructScalar>(cell);
    Json::Value obj(Json::objectValue);
    for (int i = 0; i < cell->type->num_fields(); ++i) {
      obj[cell->type->field(i)->name()] = ScalarToJson(s->value[static_cast<std::size_t>(i)]);
    }
    return obj;
  }
  case arrow::Type::LIST:
  case arrow::Type::LARGE_LIST:
  case arrow::Type::FIXED_SIZE_LIST:
  case arrow::Type::MAP: {
    auto l = std::static_pointer_cast<arrow::BaseListScalar>(cell);
    Json::Value arr(Json::arrayValue);
    for (int64_t i = 0; i < l->value->length(); ++i) {
      auto elem = l->value->GetScalar(i);
      arr.append(elem.ok() ? ScalarToJson(*elem) : Json::Value(Json::nullValue));
    }
    return arr;
  }
  default:
    return Json::Value(cell->ToString());
  }
}

std::string RenderScalar(const std::shared_ptr<arrow::Scalar> &cell, bool nested) {
  if (!cell->is_valid) {
    return nested ? "null" : "";
  }
  if (nested) {
    Json::StreamWriterBuilder builder;
    builder["indentation"] = "  ";
    return Json::writeString(builder, ScalarToJson(cell));
  }
  switch (cell->type->id()) {
  case arrow::Type::BOOL:
    return std::static_pointer_cast<arrow::BooleanScalar>(cell)->value ? "true"
                                                                       : "false";
  case arrow::Type::INT32:
    return std::to_string(std::static_pointer_cast<arrow::Int32Scalar>(cell)->value);
  case arrow::Type::INT64:
    return std::to_string(std::static_pointer_cast<arrow::Int64Scalar>(cell)->value);
  case arrow::Type::STRING:
    return std::static_pointer_cast<arrow::StringScalar>(cell)->value->ToString();
  default:
    return cell->ToString();
  }
}

arrow::Result<ParquetTable> BuildTable(const std::string &bytes) {
  ARROW_ASSIGN_OR_RAISE(std::shared_ptr<arrow::Table> table, OpenParquetTable(bytes));

  ParquetTable out;
  out.column_names = table->ColumnNames();
  out.nested_columns.resize(table->num_columns());
  for (int c = 0; c < table->num_columns(); ++c) {
    out.nested_columns[static_cast<std::size_t>(c)] =
        IsNestedTypeId(table->schema()->field(c)->type()->id());
  }
  out.rows.resize(table->num_rows());
  for (int64_t r = 0; r < table->num_rows(); ++r) {
    out.rows[static_cast<std::size_t>(r)].resize(table->num_columns());
    for (int c = 0; c < table->num_columns(); ++c) {
      ARROW_ASSIGN_OR_RAISE(auto cell, table->column(c)->GetScalar(r));
      out.rows[static_cast<std::size_t>(r)][static_cast<std::size_t>(c)] =
          RenderScalar(cell, out.nested_columns[static_cast<std::size_t>(c)]);
    }
  }
  return out;
}

} // namespace

arrow::Result<std::shared_ptr<arrow::Table>> OpenParquetTable(const std::string &bytes) {
  std::shared_ptr<arrow::io::RandomAccessFile> file =
      arrow::io::BufferReader::FromString(bytes);

  ARROW_ASSIGN_OR_RAISE(
      std::unique_ptr<parquet::arrow::FileReader> file_reader,
      parquet::arrow::OpenFile(file, arrow::default_memory_pool()));
  ARROW_ASSIGN_OR_RAISE(std::shared_ptr<arrow::Table> table, file_reader->ReadTable());
  return table;
}

ParquetOutcome ParseParquetTable(const std::string &bytes) {
  auto result = BuildTable(bytes);
  if (!result.ok()) {
    return ParquetOutcome{{}, result.status().ToString()};
  }
  return ParquetOutcome{std::move(result).ValueOrDie(), ""};
}

} // namespace blackkeys::assetsbo::storage
