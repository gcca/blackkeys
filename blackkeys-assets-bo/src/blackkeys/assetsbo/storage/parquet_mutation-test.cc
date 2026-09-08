#include "blackkeys/assetsbo/storage/parquet_mutation.hpp"

#include "blackkeys/assetsbo/storage/parquet_table.hpp"

#include <cstdint>
#include <memory>
#include <vector>

#include <arrow/array/builder_binary.h>
#include <arrow/array/builder_nested.h>
#include <arrow/array/builder_primitive.h>
#include <arrow/io/memory.h>
#include <arrow/table.h>
#include <arrow/type.h>
#include <arrow/util/logging.h>
#include <gtest/gtest.h>
#include <json/json.h>
#include <parquet/arrow/writer.h>

namespace {

using blackkeys::assetsbo::storage::AppendRow;
using blackkeys::assetsbo::storage::ParseParquetTable;
using blackkeys::assetsbo::storage::RemoveRow;
using blackkeys::assetsbo::storage::ReplaceCells;

// Column layout: id (int32, scalar), subcategory (struct{id:int32}, a bare
// struct like the real "tags" column), stores (list<struct{id:int32,
// name:utf8}>, like the real "stores"/"amenities" columns), active (bool,
// scalar), name (string scalar). Two rows:
//   row 0: id=1, subcategory={id:7}, stores=[{id:10,"A"}], active=true, name=alpha
//   row 1: id=2, subcategory={id:9}, stores=[{id:20,"B"},{id:21,"C"}],
//          active=false, name=beta
std::string BuildSampleParquetBytes() {
  arrow::Int32Builder id_builder;
  ARROW_CHECK_OK(id_builder.AppendValues(std::vector<int32_t>{1, 2}));
  std::shared_ptr<arrow::Array> id_array;
  ARROW_CHECK_OK(id_builder.Finish(&id_array));

  auto subcategory_type = arrow::struct_({arrow::field("id", arrow::int32())});
  auto subcategory_id_builder = std::make_shared<arrow::Int32Builder>();
  arrow::StructBuilder subcategory_builder(
      subcategory_type, arrow::default_memory_pool(), {subcategory_id_builder});
  ARROW_CHECK_OK(subcategory_builder.Append());
  ARROW_CHECK_OK(subcategory_id_builder->Append(7));
  ARROW_CHECK_OK(subcategory_builder.Append());
  ARROW_CHECK_OK(subcategory_id_builder->Append(9));
  std::shared_ptr<arrow::Array> subcategory_array;
  ARROW_CHECK_OK(subcategory_builder.Finish(&subcategory_array));

  auto store_type =
      arrow::struct_({arrow::field("id", arrow::int32()), arrow::field("name", arrow::utf8())});
  auto store_id_builder = std::make_shared<arrow::Int32Builder>();
  auto store_name_builder = std::make_shared<arrow::StringBuilder>();
  auto store_struct_builder = std::make_shared<arrow::StructBuilder>(
      store_type, arrow::default_memory_pool(),
      std::vector<std::shared_ptr<arrow::ArrayBuilder>>{store_id_builder,
                                                        store_name_builder});
  arrow::ListBuilder stores_builder(arrow::default_memory_pool(), store_struct_builder);

  ARROW_CHECK_OK(stores_builder.Append());
  ARROW_CHECK_OK(store_struct_builder->Append());
  ARROW_CHECK_OK(store_id_builder->Append(10));
  ARROW_CHECK_OK(store_name_builder->Append("A"));

  ARROW_CHECK_OK(stores_builder.Append());
  ARROW_CHECK_OK(store_struct_builder->Append());
  ARROW_CHECK_OK(store_id_builder->Append(20));
  ARROW_CHECK_OK(store_name_builder->Append("B"));
  ARROW_CHECK_OK(store_struct_builder->Append());
  ARROW_CHECK_OK(store_id_builder->Append(21));
  ARROW_CHECK_OK(store_name_builder->Append("C"));

  std::shared_ptr<arrow::Array> stores_array;
  ARROW_CHECK_OK(stores_builder.Finish(&stores_array));

  arrow::BooleanBuilder active_builder;
  ARROW_CHECK_OK(active_builder.AppendValues(std::vector<bool>{true, false}));
  std::shared_ptr<arrow::Array> active_array;
  ARROW_CHECK_OK(active_builder.Finish(&active_array));

  arrow::StringBuilder name_builder;
  ARROW_CHECK_OK(name_builder.AppendValues(
      std::vector<std::string>{"alpha", "beta"}));
  std::shared_ptr<arrow::Array> name_array;
  ARROW_CHECK_OK(name_builder.Finish(&name_array));

  auto schema = arrow::schema({arrow::field("id", arrow::int32()),
                              arrow::field("subcategory", subcategory_type),
                              arrow::field("stores", arrow::list(store_type)),
                              arrow::field("active", arrow::boolean()),
                              arrow::field("name", arrow::utf8())});
  auto table = arrow::Table::Make(
      schema, {id_array, subcategory_array, stores_array, active_array,
               name_array});

  auto sink = arrow::io::BufferOutputStream::Create().ValueOrDie();
  ARROW_CHECK_OK(parquet::arrow::WriteTable(*table, arrow::default_memory_pool(), sink, 1024));
  auto buffer = sink->Finish().ValueOrDie();
  return std::string(reinterpret_cast<const char *>(buffer->data()), buffer->size());
}

Json::Value ParseJson(const std::string &text) {
  Json::CharReaderBuilder builder;
  std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
  Json::Value root;
  std::string errors;
  const bool ok = reader->parse(text.data(), text.data() + text.size(), &root, &errors);
  EXPECT_TRUE(ok) << "not valid JSON: " << text << " (" << errors << ")";
  return root;
}

constexpr std::size_t kIdColumn = 0;
constexpr std::size_t kSubcategoryColumn = 1;
constexpr std::size_t kStoresColumn = 2;
constexpr std::size_t kActiveColumn = 3;
constexpr std::size_t kNameColumn = 4;

TEST(ParquetMutation, ReplacesStructCellOnTargetRowOnly) {
  const auto original = BuildSampleParquetBytes();
  const auto outcome =
      ReplaceCells(original, 0, {{kSubcategoryColumn, R"({"id": 100})"}});
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  EXPECT_EQ(ParseJson(table.rows[0][kSubcategoryColumn])["id"].asInt(), 100);
  EXPECT_EQ(ParseJson(table.rows[1][kSubcategoryColumn])["id"].asInt(), 9);
  EXPECT_EQ(table.rows[0][kIdColumn], "1");
  EXPECT_EQ(table.rows[1][kIdColumn], "2");
  EXPECT_EQ(ParseJson(table.rows[0][kStoresColumn])[0]["id"].asInt(), 10);
  EXPECT_EQ(ParseJson(table.rows[1][kStoresColumn]).size(), 2u);
}

TEST(ParquetMutation, ReplacesListStructCellOnTargetRowOnly) {
  const auto original = BuildSampleParquetBytes();
  const auto outcome =
      ReplaceCells(original, 1, {{kStoresColumn, R"([{"id": 99, "name": "Z"}])"}});
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  const auto stores1 = ParseJson(table.rows[1][kStoresColumn]);
  ASSERT_EQ(stores1.size(), 1u);
  EXPECT_EQ(stores1[0]["id"].asInt(), 99);
  EXPECT_EQ(stores1[0]["name"].asString(), "Z");

  const auto stores0 = ParseJson(table.rows[0][kStoresColumn]);
  ASSERT_EQ(stores0.size(), 1u);
  EXPECT_EQ(stores0[0]["id"].asInt(), 10);
}

TEST(ParquetMutation, MalformedJsonReturnsError) {
  const auto outcome =
      ReplaceCells(BuildSampleParquetBytes(), 0, {{kSubcategoryColumn, "{not json"}});
  EXPECT_FALSE(outcome.error.empty());
  EXPECT_TRUE(outcome.bytes.empty());
}

TEST(ParquetMutation, JsonShapeMismatchReturnsError) {
  // "id" is declared int32; a JSON string for it must be rejected, not
  // silently coerced (jsoncpp's asInt() throws on a real type mismatch,
  // which JsonToScalar must guard against with an isInt() check first).
  const auto outcome = ReplaceCells(BuildSampleParquetBytes(), 0,
                                    {{kSubcategoryColumn, R"({"id": "not a number"})"}});
  EXPECT_FALSE(outcome.error.empty());
  EXPECT_TRUE(outcome.bytes.empty());
}

TEST(ParquetMutation, ReplacesScalarNameWhilePreservingEveryOtherCell) {
  const auto outcome =
      ReplaceCells(BuildSampleParquetBytes(), 0, {{kNameColumn, "renamed"}});
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  ASSERT_EQ(table.rows.size(), 2u);
  ASSERT_EQ(table.column_names.size(), 5u);
  EXPECT_EQ(table.rows[0][kNameColumn], "renamed");
  EXPECT_EQ(table.rows[1][kNameColumn], "beta");
  EXPECT_EQ(table.rows[0][kIdColumn], "1");
  EXPECT_EQ(table.rows[1][kIdColumn], "2");
  EXPECT_EQ(ParseJson(table.rows[0][kSubcategoryColumn])["id"].asInt(), 7);
  EXPECT_EQ(ParseJson(table.rows[1][kSubcategoryColumn])["id"].asInt(), 9);
  EXPECT_EQ(ParseJson(table.rows[0][kStoresColumn])[0]["name"].asString(),
            "A");
  EXPECT_EQ(ParseJson(table.rows[1][kStoresColumn]).size(), 2u);
  EXPECT_EQ(table.rows[0][kActiveColumn], "true");
  EXPECT_EQ(table.rows[1][kActiveColumn], "false");
}

TEST(ParquetMutation, NullEditProducesNullCell) {
  const auto outcome = ReplaceCells(BuildSampleParquetBytes(), 0,
                                    {{kSubcategoryColumn, "null"}});
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  EXPECT_EQ(parsed.table.rows[0][kSubcategoryColumn], "null");
}

TEST(ParquetMutation, AppliesMultipleColumnEditsInOnePass) {
  const auto outcome =
      ReplaceCells(BuildSampleParquetBytes(), 0,
                  {{kSubcategoryColumn, R"({"id": 42})"},
                   {kStoresColumn, R"([{"id": 1, "name": "Solo"}])"}});
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  EXPECT_EQ(ParseJson(table.rows[0][kSubcategoryColumn])["id"].asInt(), 42);
  const auto stores0 = ParseJson(table.rows[0][kStoresColumn]);
  ASSERT_EQ(stores0.size(), 1u);
  EXPECT_EQ(stores0[0]["name"].asString(), "Solo");
}

TEST(ParquetMutation, AppendsRowWithScalarAndNestedFields) {
  const auto original = BuildSampleParquetBytes();
  const auto outcome =
      AppendRow(original, {{kIdColumn, "3"},
                          {kSubcategoryColumn, R"({"id": 55})"},
                          {kStoresColumn, R"([{"id": 30, "name": "D"}])"},
                          {kActiveColumn, "true"}});
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  ASSERT_EQ(table.rows.size(), 3u);
  EXPECT_EQ(table.rows[0][kIdColumn], "1");
  EXPECT_EQ(table.rows[1][kIdColumn], "2");
  EXPECT_EQ(table.rows[2][kIdColumn], "3");
  EXPECT_EQ(ParseJson(table.rows[2][kSubcategoryColumn])["id"].asInt(), 55);
  const auto stores2 = ParseJson(table.rows[2][kStoresColumn]);
  ASSERT_EQ(stores2.size(), 1u);
  EXPECT_EQ(stores2[0]["name"].asString(), "D");
  EXPECT_EQ(table.rows[2][kActiveColumn], "true");

  // Pre-existing rows are untouched.
  EXPECT_EQ(ParseJson(table.rows[0][kSubcategoryColumn])["id"].asInt(), 7);
  EXPECT_EQ(table.rows[1][kActiveColumn], "false");
}

TEST(ParquetMutation, AppendedRowLeavesUnsubmittedColumnsNull) {
  const auto outcome = AppendRow(BuildSampleParquetBytes(), {{kIdColumn, "3"}});
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  ASSERT_EQ(table.rows.size(), 3u);
  EXPECT_EQ(table.rows[2][kIdColumn], "3");
  EXPECT_EQ(table.rows[2][kSubcategoryColumn], "null");
  EXPECT_EQ(table.rows[2][kStoresColumn], "null");
  EXPECT_EQ(table.rows[2][kActiveColumn], "");
}

TEST(ParquetMutation, AppendRowMalformedJsonForNestedColumnReturnsError) {
  const auto outcome =
      AppendRow(BuildSampleParquetBytes(), {{kSubcategoryColumn, "{not json"}});
  EXPECT_FALSE(outcome.error.empty());
  EXPECT_TRUE(outcome.bytes.empty());
}

TEST(ParquetMutation, AppendRowMalformedScalarTextReturnsError) {
  const auto outcome = AppendRow(BuildSampleParquetBytes(), {{kIdColumn, "abc"}});
  EXPECT_FALSE(outcome.error.empty());
  EXPECT_TRUE(outcome.bytes.empty());
}

TEST(ParquetMutation, AppendRowOutOfRangeColumnIndexReturnsError) {
  const auto outcome = AppendRow(BuildSampleParquetBytes(), {{99, "x"}});
  EXPECT_FALSE(outcome.error.empty());
  EXPECT_TRUE(outcome.bytes.empty());
}

TEST(ParquetMutation, RemovesFirstRowLeavingSecondIntact) {
  const auto outcome = RemoveRow(BuildSampleParquetBytes(), 0);
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  ASSERT_EQ(table.rows.size(), 1u);
  EXPECT_EQ(table.rows[0][kIdColumn], "2");
  EXPECT_EQ(ParseJson(table.rows[0][kSubcategoryColumn])["id"].asInt(), 9);
  const auto stores = ParseJson(table.rows[0][kStoresColumn]);
  ASSERT_EQ(stores.size(), 2u);
  EXPECT_EQ(stores[0]["id"].asInt(), 20);
  EXPECT_EQ(stores[1]["id"].asInt(), 21);
  EXPECT_EQ(table.rows[0][kActiveColumn], "false");
}

TEST(ParquetMutation, RemovesSecondRowLeavingFirstIntact) {
  const auto outcome = RemoveRow(BuildSampleParquetBytes(), 1);
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto parsed = ParseParquetTable(outcome.bytes);
  ASSERT_TRUE(parsed.error.empty()) << parsed.error;
  const auto &table = parsed.table;

  ASSERT_EQ(table.rows.size(), 1u);
  EXPECT_EQ(table.rows[0][kIdColumn], "1");
  EXPECT_EQ(ParseJson(table.rows[0][kSubcategoryColumn])["id"].asInt(), 7);
  const auto stores = ParseJson(table.rows[0][kStoresColumn]);
  ASSERT_EQ(stores.size(), 1u);
  EXPECT_EQ(stores[0]["id"].asInt(), 10);
  EXPECT_EQ(table.rows[0][kActiveColumn], "true");
}

TEST(ParquetMutation, RemoveRowOutOfRangeIndexReturnsError) {
  const auto outcome = RemoveRow(BuildSampleParquetBytes(), 99);
  EXPECT_FALSE(outcome.error.empty());
  EXPECT_TRUE(outcome.bytes.empty());
}

} // namespace
