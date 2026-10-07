#include "blackkeys/assetsbo/storage/parquet_mutation.hpp"
#include "blackkeys/assetsbo/storage/timestamp.hpp"

#include "blackkeys/assetsbo/storage/parquet_table.hpp"

#include <algorithm>
#include <cctype>
#include <exception>
#include <memory>
#include <utility>

#include <arrow/array/builder_base.h>
#include <arrow/chunked_array.h>
#include <arrow/io/memory.h>
#include <arrow/result.h>
#include <arrow/scalar.h>
#include <arrow/status.h>
#include <arrow/table.h>
#include <arrow/type.h>
#include <json/json.h>
#include <parquet/arrow/writer.h>

namespace blackkeys::assetsbo::storage {
namespace {

bool IsEditableTypeId(arrow::Type::type id) {
  switch (id) {
  case arrow::Type::STRUCT:
  case arrow::Type::LIST:
  case arrow::Type::LARGE_LIST:
  case arrow::Type::FIXED_SIZE_LIST:
    return true;
  default:
    return false;
  }
}

bool IsBlank(const std::string &text);

arrow::Result<std::shared_ptr<arrow::Scalar>>
ParseScalarText(const std::string &text,
                const std::shared_ptr<arrow::DataType> &type);

arrow::Result<std::shared_ptr<arrow::Scalar>>
JsonToScalar(const Json::Value &json, const std::shared_ptr<arrow::DataType> &type) {
  if (json.isNull()) {
    return arrow::MakeNullScalar(type);
  }
  switch (type->id()) {
  case arrow::Type::BOOL:
    if (!json.isBool()) {
      return arrow::Status::Invalid("expected a JSON boolean for a bool field");
    }
    return std::make_shared<arrow::BooleanScalar>(json.asBool());
  case arrow::Type::INT32:
    if (!json.isInt()) {
      return arrow::Status::Invalid("expected a JSON integer for an int32 field");
    }
    return std::make_shared<arrow::Int32Scalar>(json.asInt());
  case arrow::Type::INT64:
    if (!json.isInt64() && !json.isInt()) {
      return arrow::Status::Invalid("expected a JSON integer for an int64 field");
    }
    return std::make_shared<arrow::Int64Scalar>(json.asInt64());
  case arrow::Type::STRING:
    if (!json.isString()) {
      return arrow::Status::Invalid("expected a JSON string for a string field");
    }
    return std::make_shared<arrow::StringScalar>(json.asString());
  case arrow::Type::STRUCT: {
    if (!json.isObject()) {
      return arrow::Status::Invalid("expected a JSON object for a struct field");
    }
    std::vector<std::shared_ptr<arrow::Scalar>> children;
    children.reserve(static_cast<std::size_t>(type->num_fields()));
    for (int i = 0; i < type->num_fields(); ++i) {
      ARROW_ASSIGN_OR_RAISE(
          auto child,
          JsonToScalar(json[type->field(i)->name()], type->field(i)->type()));
      children.push_back(std::move(child));
    }
    return std::make_shared<arrow::StructScalar>(std::move(children), type);
  }
  case arrow::Type::LIST:
  case arrow::Type::LARGE_LIST:
  case arrow::Type::FIXED_SIZE_LIST: {
    if (!json.isArray()) {
      return arrow::Status::Invalid("expected a JSON array for a list field");
    }
    const auto child_type =
        std::static_pointer_cast<arrow::BaseListType>(type)->value_type();
    ARROW_ASSIGN_OR_RAISE(auto builder, arrow::MakeBuilder(child_type));
    for (const auto &elem : json) {
      ARROW_ASSIGN_OR_RAISE(auto child, JsonToScalar(elem, child_type));
      ARROW_RETURN_NOT_OK(builder->AppendScalar(*child));
    }
    ARROW_ASSIGN_OR_RAISE(auto child_array, builder->Finish());
    switch (type->id()) {
    case arrow::Type::LIST:
      return std::make_shared<arrow::ListScalar>(child_array, type);
    case arrow::Type::LARGE_LIST:
      return std::make_shared<arrow::LargeListScalar>(child_array, type);
    default:
      return std::make_shared<arrow::FixedSizeListScalar>(child_array, type);
    }
  }
  default:
    return arrow::Status::Invalid("unsupported column type for editing");
  }
}

arrow::Result<std::shared_ptr<arrow::Table>>
ApplyEdit(std::shared_ptr<arrow::Table> table, std::size_t row_index,
         const CellEdit &edit) {
  if (edit.column_index >= static_cast<std::size_t>(table->num_columns())) {
    return arrow::Status::Invalid("column index out of range");
  }
  const auto col_idx = static_cast<int>(edit.column_index);
  const auto field = table->schema()->field(col_idx);
  const auto type = field->type();

  std::shared_ptr<arrow::Scalar> new_scalar;
  if (edit.binary) {
    if (type->id() != arrow::Type::BINARY && type->id() != arrow::Type::LARGE_BINARY)
      return arrow::Status::Invalid("raw bytes require a binary column");
    if (type->id() == arrow::Type::BINARY)
      new_scalar = std::make_shared<arrow::BinaryScalar>(arrow::Buffer::FromString(*edit.binary));
    else
      new_scalar = std::make_shared<arrow::LargeBinaryScalar>(arrow::Buffer::FromString(*edit.binary));
  } else if (IsEditableTypeId(type->id())) {
    Json::CharReaderBuilder reader_builder;
    reader_builder["failIfExtra"] = true;
    std::unique_ptr<Json::CharReader> reader(reader_builder.newCharReader());
    Json::Value parsed;
    std::string errors;
    if (!reader->parse(edit.text.data(), edit.text.data() + edit.text.size(),
                       &parsed, &errors)) {
      return arrow::Status::Invalid(
          "invalid JSON for column \"" + field->name() + "\": " +
          (errors.empty() ? "parse error" : errors));
    }
    ARROW_ASSIGN_OR_RAISE(new_scalar, JsonToScalar(parsed, type));
  } else {
    ARROW_ASSIGN_OR_RAISE(new_scalar, ParseScalarText(edit.text, type));
  }
  ARROW_RETURN_NOT_OK(new_scalar->Validate());

  auto old_array = table->column(col_idx)->chunk(0);
  if (row_index >= static_cast<std::size_t>(old_array->length())) {
    return arrow::Status::Invalid("row index out of range");
  }

  ARROW_ASSIGN_OR_RAISE(auto builder, arrow::MakeBuilder(type));
  for (int64_t i = 0; i < old_array->length(); ++i) {
    if (static_cast<std::size_t>(i) == row_index) {
      ARROW_RETURN_NOT_OK(builder->AppendScalar(*new_scalar));
    } else {
      ARROW_ASSIGN_OR_RAISE(auto existing, old_array->GetScalar(i));
      ARROW_RETURN_NOT_OK(builder->AppendScalar(*existing));
    }
  }
  ARROW_ASSIGN_OR_RAISE(auto new_array, builder->Finish());
  auto new_chunked = std::make_shared<arrow::ChunkedArray>(new_array);
  ARROW_ASSIGN_OR_RAISE(auto new_table, table->SetColumn(col_idx, field, new_chunked));
  return new_table;
}

arrow::Result<std::string> SerializeTable(const arrow::Table &table) {
  ARROW_ASSIGN_OR_RAISE(auto sink, arrow::io::BufferOutputStream::Create());
  ARROW_RETURN_NOT_OK(
      parquet::arrow::WriteTable(table, arrow::default_memory_pool(), sink, 1024 * 1024, parquet::WriterProperties::Builder().build(), parquet::ArrowWriterProperties::Builder().store_schema()->build()));
  ARROW_ASSIGN_OR_RAISE(auto buffer, sink->Finish());
  return std::string(reinterpret_cast<const char *>(buffer->data()),
                     static_cast<std::size_t>(buffer->size()));
}

bool IsBlank(const std::string &text) {
  return std::ranges::all_of(text, [](unsigned char ch) { return std::isspace(ch) != 0; });
}

arrow::Result<std::shared_ptr<arrow::Scalar>>
ParseScalarText(const std::string &text, const std::shared_ptr<arrow::DataType> &type) {
  if (IsBlank(text)) {
    return arrow::MakeNullScalar(type);
  }
  switch (type->id()) {
  case arrow::Type::BOOL:
    if (text == "true") {
      return std::make_shared<arrow::BooleanScalar>(true);
    }
    if (text == "false") {
      return std::make_shared<arrow::BooleanScalar>(false);
    }
    return arrow::Status::Invalid("expected \"true\" or \"false\" for a bool field");
  case arrow::Type::INT32:
    try {
      std::size_t pos = 0;
      const auto value = std::stoi(text, &pos);
      if (pos != text.size()) {
        return arrow::Status::Invalid("expected an integer for an int32 field");
      }
      return std::make_shared<arrow::Int32Scalar>(value);
    } catch (const std::exception &) {
      return arrow::Status::Invalid("expected an integer for an int32 field");
    }
  case arrow::Type::INT64:
    try {
      std::size_t pos = 0;
      const auto value = std::stoll(text, &pos);
      if (pos != text.size()) {
        return arrow::Status::Invalid("expected an integer for an int64 field");
      }
      return std::make_shared<arrow::Int64Scalar>(static_cast<int64_t>(value));
    } catch (const std::exception &) {
      return arrow::Status::Invalid("expected an integer for an int64 field");
    }
  case arrow::Type::TIMESTAMP: {
    const auto timestamp = std::static_pointer_cast<arrow::TimestampType>(type);
    ARROW_ASSIGN_OR_RAISE(auto value, ParseTimestamp(text, timestamp->unit()));
    return std::make_shared<arrow::TimestampScalar>(value, type);
  }
  case arrow::Type::STRING:
    return std::make_shared<arrow::StringScalar>(text);
  default:
    return arrow::Status::Invalid("unsupported column type for creation");
  }
}

arrow::Result<std::shared_ptr<arrow::Scalar>>
NewCellScalar(const std::string &text, const std::shared_ptr<arrow::DataType> &type) {
  if (!IsEditableTypeId(type->id())) {
    return ParseScalarText(text, type);
  }
  if (IsBlank(text)) {
    return JsonToScalar(Json::Value(), type);
  }
  Json::CharReaderBuilder reader_builder;
  reader_builder["failIfExtra"] = true;
  std::unique_ptr<Json::CharReader> reader(reader_builder.newCharReader());
  Json::Value parsed;
  std::string errors;
  if (!reader->parse(text.data(), text.data() + text.size(), &parsed, &errors)) {
    return arrow::Status::Invalid("invalid JSON: " + (errors.empty() ? "parse error" : errors));
  }
  return JsonToScalar(parsed, type);
}

// Builds the full replacement array for one column: every existing value
// followed by `new_scalar`. Unlike ApplyEdit's per-row rebuild, this changes
// the column's length, so the result cannot be installed one column at a
// time via Table::SetColumn (which requires the new column to match the
// table's *current* row count) -- every column's new array must be built
// first and the whole table reconstructed from them at once.
arrow::Result<std::shared_ptr<arrow::Array>>
BuildAppendedColumn(const std::shared_ptr<arrow::Array> &old_array,
                    const std::shared_ptr<arrow::DataType> &type,
                    const std::shared_ptr<arrow::Scalar> &new_scalar) {
  ARROW_ASSIGN_OR_RAISE(auto builder, arrow::MakeBuilder(type));
  for (int64_t i = 0; i < old_array->length(); ++i) {
    ARROW_ASSIGN_OR_RAISE(auto existing, old_array->GetScalar(i));
    ARROW_RETURN_NOT_OK(builder->AppendScalar(*existing));
  }
  ARROW_RETURN_NOT_OK(builder->AppendScalar(*new_scalar));
  return builder->Finish();
}

// Builds the full replacement array for one column with `row_index` omitted:
// every existing value except the one at `row_index`. Mirrors
// BuildAppendedColumn's shape, but shrinks rather than grows the column, so
// (for the same reason as AppendRow) the whole table must be reconstructed in
// one shot from every column's already-shrunk array, not installed one column
// at a time via Table::SetColumn.
arrow::Result<std::shared_ptr<arrow::Array>>
BuildRemovedColumn(const std::shared_ptr<arrow::Array> &old_array,
                   const std::shared_ptr<arrow::DataType> &type,
                   std::size_t row_index) {
  ARROW_ASSIGN_OR_RAISE(auto builder, arrow::MakeBuilder(type));
  for (int64_t i = 0; i < old_array->length(); ++i) {
    if (static_cast<std::size_t>(i) == row_index) {
      continue;
    }
    ARROW_ASSIGN_OR_RAISE(auto existing, old_array->GetScalar(i));
    ARROW_RETURN_NOT_OK(builder->AppendScalar(*existing));
  }
  return builder->Finish();
}

arrow::Result<std::string> RemoveRowImpl(const std::string &parquet_bytes,
                                         std::size_t row_index) {
  ARROW_ASSIGN_OR_RAISE(std::shared_ptr<arrow::Table> table,
                        OpenParquetTable(parquet_bytes));
  ARROW_ASSIGN_OR_RAISE(table, table->CombineChunks());

  if (row_index >= static_cast<std::size_t>(table->num_rows())) {
    return arrow::Status::Invalid("row index out of range");
  }

  std::vector<std::shared_ptr<arrow::Array>> new_columns;
  new_columns.reserve(static_cast<std::size_t>(table->num_columns()));
  for (int col_idx = 0; col_idx < table->num_columns(); ++col_idx) {
    const auto type = table->schema()->field(col_idx)->type();
    auto old_array = table->column(col_idx)->chunk(0);
    ARROW_ASSIGN_OR_RAISE(auto new_array,
                          BuildRemovedColumn(old_array, type, row_index));
    new_columns.push_back(std::move(new_array));
  }

  auto new_table = arrow::Table::Make(table->schema(), new_columns);
  return SerializeTable(*new_table);
}

arrow::Result<std::string> AppendRowImpl(const std::string &parquet_bytes,
                                         const std::vector<NewCell> &cells) {
  ARROW_ASSIGN_OR_RAISE(std::shared_ptr<arrow::Table> table,
                        OpenParquetTable(parquet_bytes));
  ARROW_ASSIGN_OR_RAISE(table, table->CombineChunks());

  std::vector<std::string> texts(static_cast<std::size_t>(table->num_columns()));
  std::vector<std::optional<std::string>> binaries(texts.size());
  for (const auto &cell : cells) {
    if (cell.column_index >= texts.size()) {
      return arrow::Status::Invalid("column index out of range");
    }
    texts[cell.column_index] = cell.text;
    binaries[cell.column_index] = cell.binary;
  }

  std::vector<std::shared_ptr<arrow::Array>> new_columns;
  new_columns.reserve(texts.size());
  for (int col_idx = 0; col_idx < table->num_columns(); ++col_idx) {
    const auto type = table->schema()->field(col_idx)->type();
    std::shared_ptr<arrow::Scalar> new_scalar;
    if (binaries[col_idx]) {
      if (type->id() != arrow::Type::BINARY && type->id() != arrow::Type::LARGE_BINARY)
        return arrow::Status::Invalid("raw bytes require a binary column");
      if (type->id() == arrow::Type::BINARY)
        new_scalar = std::make_shared<arrow::BinaryScalar>(arrow::Buffer::FromString(*binaries[col_idx]));
      else
        new_scalar = std::make_shared<arrow::LargeBinaryScalar>(arrow::Buffer::FromString(*binaries[col_idx]));
    } else {
      ARROW_ASSIGN_OR_RAISE(new_scalar, NewCellScalar(texts[col_idx], type));
    }
    ARROW_RETURN_NOT_OK(new_scalar->Validate());

    auto old_array = table->column(col_idx)->chunk(0);
    ARROW_ASSIGN_OR_RAISE(auto new_array,
                          BuildAppendedColumn(old_array, type, new_scalar));
    new_columns.push_back(std::move(new_array));
  }

  auto new_table = arrow::Table::Make(table->schema(), new_columns);
  return SerializeTable(*new_table);
}

arrow::Result<std::string> ReplaceCellsImpl(const std::string &parquet_bytes,
                                            std::size_t row_index,
                                            const std::vector<CellEdit> &edits) {
  ARROW_ASSIGN_OR_RAISE(std::shared_ptr<arrow::Table> table,
                        OpenParquetTable(parquet_bytes));
  ARROW_ASSIGN_OR_RAISE(table, table->CombineChunks());

  if (row_index >= static_cast<std::size_t>(table->num_rows()))
    return arrow::Status::Invalid("row index out of range");
  for (const auto &edit : edits) {
    ARROW_ASSIGN_OR_RAISE(table, ApplyEdit(table, row_index, edit));
  }

  return SerializeTable(*table);
}

} // namespace

MutationOutcome ReplaceCells(const std::string &parquet_bytes, std::size_t row_index,
                             const std::vector<CellEdit> &edits) {
  auto result = ReplaceCellsImpl(parquet_bytes, row_index, edits);
  if (!result.ok()) {
    return MutationOutcome{"", result.status().ToString()};
  }
  return MutationOutcome{std::move(result).ValueOrDie(), ""};
}

MutationOutcome AppendRow(const std::string &parquet_bytes,
                         const std::vector<NewCell> &cells) {
  auto result = AppendRowImpl(parquet_bytes, cells);
  if (!result.ok()) {
    return MutationOutcome{"", result.status().ToString()};
  }
  return MutationOutcome{std::move(result).ValueOrDie(), ""};
}

MutationOutcome RemoveRow(const std::string &parquet_bytes, std::size_t row_index) {
  auto result = RemoveRowImpl(parquet_bytes, row_index);
  if (!result.ok()) {
    return MutationOutcome{"", result.status().ToString()};
  }
  return MutationOutcome{std::move(result).ValueOrDie(), ""};
}

} // namespace blackkeys::assetsbo::storage
