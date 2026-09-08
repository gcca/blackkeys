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

using blackkeys::assetsbo::storage::ParseParquetTable;

Json::Value ParseJson(const std::string &text) {
  Json::CharReaderBuilder builder;
  std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
  Json::Value root;
  std::string errors;
  const bool ok =
      reader->parse(text.data(), text.data() + text.size(), &root, &errors);
  EXPECT_TRUE(ok) << "not valid JSON: " << text << " (" << errors << ")";
  return root;
}

std::string BuildSampleParquetBytes() {
  arrow::Int32Builder id_builder;
  ARROW_CHECK_OK(id_builder.AppendValues(std::vector<int32_t>{1, 2, 3}));
  std::shared_ptr<arrow::Array> id_array;
  ARROW_CHECK_OK(id_builder.Finish(&id_array));

  arrow::StringBuilder name_builder;
  ARROW_CHECK_OK(name_builder.Append("ADIDAS"));
  ARROW_CHECK_OK(name_builder.AppendNull());
  ARROW_CHECK_OK(name_builder.Append("NIKE"));
  std::shared_ptr<arrow::Array> name_array;
  ARROW_CHECK_OK(name_builder.Finish(&name_array));

  arrow::BooleanBuilder active_builder;
  ARROW_CHECK_OK(active_builder.AppendValues(std::vector<bool>{true, false, true}));
  std::shared_ptr<arrow::Array> active_array;
  ARROW_CHECK_OK(active_builder.Finish(&active_array));

  auto nested_field = arrow::field("id", arrow::int32());
  auto struct_type = arrow::struct_({nested_field});
  auto nested_id_builder = std::make_shared<arrow::Int32Builder>();
  arrow::StructBuilder subcategory_builder(struct_type, arrow::default_memory_pool(),
                                           {nested_id_builder});
  ARROW_CHECK_OK(subcategory_builder.Append());
  ARROW_CHECK_OK(nested_id_builder->Append(7));
  ARROW_CHECK_OK(subcategory_builder.Append());
  ARROW_CHECK_OK(nested_id_builder->Append(9));
  ARROW_CHECK_OK(subcategory_builder.AppendNull());
  std::shared_ptr<arrow::Array> subcategory_array;
  ARROW_CHECK_OK(subcategory_builder.Finish(&subcategory_array));

  auto store_id_field = arrow::field("id", arrow::int32());
  auto store_name_field = arrow::field("name", arrow::utf8());
  auto store_type = arrow::struct_({store_id_field, store_name_field});
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

  ARROW_CHECK_OK(stores_builder.Append());
  ARROW_CHECK_OK(store_struct_builder->Append());
  ARROW_CHECK_OK(store_id_builder->Append(20));
  ARROW_CHECK_OK(store_name_builder->Append("B"));
  ARROW_CHECK_OK(store_struct_builder->Append());
  ARROW_CHECK_OK(store_id_builder->Append(21));
  ARROW_CHECK_OK(store_name_builder->Append("C"));

  std::shared_ptr<arrow::Array> stores_array;
  ARROW_CHECK_OK(stores_builder.Finish(&stores_array));

  auto schema = arrow::schema({arrow::field("id", arrow::int32()),
                              arrow::field("name", arrow::utf8()),
                              arrow::field("isActive", arrow::boolean()),
                              arrow::field("subcategory", struct_type),
                              arrow::field("stores", arrow::list(store_type))});
  auto table =
      arrow::Table::Make(schema, {id_array, name_array, active_array,
                                  subcategory_array, stores_array});

  auto sink = arrow::io::BufferOutputStream::Create().ValueOrDie();
  ARROW_CHECK_OK(parquet::arrow::WriteTable(*table, arrow::default_memory_pool(),
                                            sink, 1024));
  auto buffer = sink->Finish().ValueOrDie();
  return std::string(reinterpret_cast<const char *>(buffer->data()),
                     buffer->size());
}

TEST(ParquetTable, RendersPrimitiveAndNestedColumns) {
  const auto outcome = ParseParquetTable(BuildSampleParquetBytes());
  ASSERT_TRUE(outcome.error.empty()) << outcome.error;

  const auto &table = outcome.table;
  ASSERT_EQ(table.column_names.size(), 5u);
  EXPECT_EQ(table.column_names[0], "id");
  EXPECT_EQ(table.column_names[1], "name");
  EXPECT_EQ(table.column_names[2], "isActive");
  EXPECT_EQ(table.column_names[3], "subcategory");
  EXPECT_EQ(table.column_names[4], "stores");

  ASSERT_EQ(table.nested_columns.size(), 5u);
  EXPECT_FALSE(table.nested_columns[0]);
  EXPECT_FALSE(table.nested_columns[1]);
  EXPECT_FALSE(table.nested_columns[2]);
  EXPECT_TRUE(table.nested_columns[3]);
  EXPECT_TRUE(table.nested_columns[4]);

  ASSERT_EQ(table.rows.size(), 3u);

  EXPECT_EQ(table.rows[0][0], "1");
  EXPECT_EQ(table.rows[0][1], "ADIDAS");
  EXPECT_EQ(table.rows[0][2], "true");
  EXPECT_EQ(table.rows[1][0], "2");
  EXPECT_EQ(table.rows[1][1], "");
  EXPECT_EQ(table.rows[1][2], "false");
  EXPECT_EQ(table.rows[2][0], "3");
  EXPECT_EQ(table.rows[2][1], "NIKE");
  EXPECT_EQ(table.rows[2][2], "true");

  // subcategory: a bare struct column, one row null.
  EXPECT_EQ(ParseJson(table.rows[0][3])["id"].asInt(), 7);
  EXPECT_EQ(ParseJson(table.rows[1][3])["id"].asInt(), 9);
  EXPECT_EQ(table.rows[2][3], "null");

  // stores: a list<struct> column, one row an empty list.
  const auto stores0 = ParseJson(table.rows[0][4]);
  ASSERT_TRUE(stores0.isArray());
  ASSERT_EQ(stores0.size(), 1u);
  EXPECT_EQ(stores0[0]["id"].asInt(), 10);
  EXPECT_EQ(stores0[0]["name"].asString(), "A");

  const auto stores1 = ParseJson(table.rows[1][4]);
  ASSERT_TRUE(stores1.isArray());
  EXPECT_EQ(stores1.size(), 0u);

  const auto stores2 = ParseJson(table.rows[2][4]);
  ASSERT_TRUE(stores2.isArray());
  ASSERT_EQ(stores2.size(), 2u);
  EXPECT_EQ(stores2[0]["id"].asInt(), 20);
  EXPECT_EQ(stores2[0]["name"].asString(), "B");
  EXPECT_EQ(stores2[1]["id"].asInt(), 21);
  EXPECT_EQ(stores2[1]["name"].asString(), "C");
}

TEST(ParquetTable, ReportsErrorOnGarbageBytes) {
  const auto outcome = ParseParquetTable("not a parquet file");
  EXPECT_FALSE(outcome.error.empty());
}

} // namespace
