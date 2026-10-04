#include "blackkeys/assetsbo/handling/brand/routes/common.hpp"

#include <algorithm>
#include <iterator>

#include <gtest/gtest.h>

namespace {

using blackkeys::assetsbo::handling::brand::RenderNestedCellHtml;
using blackkeys::assetsbo::handling::brand::BrandImageKey;
using blackkeys::assetsbo::handling::brand::EncodePathSegment;
using blackkeys::assetsbo::handling::brand::ApplyOverrides;
using blackkeys::assetsbo::handling::brand::IsOverridden;
using blackkeys::assetsbo::handling::brand::ValidateWebpUpload;
using blackkeys::assetsbo::handling::brand::kMaxImageBytes;

std::string WebpBytes(std::size_t size) {
  std::string bytes(size, '\0');
  if (size >= 12) {
    bytes.replace(0, 4, "RIFF");
    bytes.replace(8, 4, "WEBP");
  }
  return bytes;
}

std::string PngBytes(std::size_t size) {
  std::string bytes(size, '\0');
  if (size >= 8) {
    const char signature[] = {'\x89', 'P', 'N', 'G', '\r', '\n', '\x1a', '\n'};
    std::copy(std::begin(signature), std::end(signature), bytes.begin());
  }
  return bytes;
}

TEST(BrandImages, BuildsFixedKeys) {
  EXPECT_EQ(BrandImageKey("acme", "logo"),
            "brands/name=acme/logo.webp");
  EXPECT_EQ(BrandImageKey("new brand", "picture"),
            "brands/name=new brand/picture.webp");
}

TEST(BrandImages, EncodesSpacesForPathSegments) {
  EXPECT_EQ(EncodePathSegment("new brand"), "new%20brand");
  EXPECT_EQ(EncodePathSegment("a+b"), "a%2Bb");
}

TEST(BrandImages, AcceptsWebpAtTenMiBBoundary) {
  EXPECT_FALSE(ValidateWebpUpload(WebpBytes(kMaxImageBytes)).has_value());
}

TEST(BrandImages, RejectsWebpOverTenMiBBoundary) {
  EXPECT_TRUE(ValidateWebpUpload(WebpBytes(kMaxImageBytes + 1)).has_value());
}

TEST(BrandImages, RejectsInvalidOrShortSignature) {
  EXPECT_TRUE(ValidateWebpUpload("not a webp").has_value());
  EXPECT_TRUE(ValidateWebpUpload("RIFF\0\0\0\0WEB").has_value());
  EXPECT_TRUE(ValidateWebpUpload("RIFF\0\0\0\0WAVE").has_value());
}

TEST(BrandImages, RejectsPngUpload) {
  EXPECT_TRUE(ValidateWebpUpload(PngBytes(64)).has_value());
}

TEST(BrandOverrides, LegacyNameOverrideCannotChangeParquetIdentity) {
  blackkeys::assetsbo::storage::ParquetTable table;
  table.column_names = {"name", "phone"};
  table.nested_columns = {false, false};
  table.rows = {{"old", "111"}};
  blackkeys::assetsbo::storage::BrandOverrides overrides = {
      {"old", {{"name", "legacy-new"}, {"phone", "222"}}}};

  ApplyOverrides(table, overrides, 0);

  EXPECT_EQ(table.rows[0][0], "old");
  EXPECT_EQ(table.rows[0][1], "222");
  EXPECT_FALSE(IsOverridden(overrides, "old", "name"));
  EXPECT_TRUE(IsOverridden(overrides, "old", "phone"));
}

TEST(RenderNestedCellHtml, RendersStructAsKeyValueTable) {
  const auto html = RenderNestedCellHtml(R"({"id":7})");
  EXPECT_NE(html.find("<table"), std::string::npos);
  EXPECT_NE(html.find("<th>id</th>"), std::string::npos);
  EXPECT_NE(html.find("<td>7</td>"), std::string::npos);
}

TEST(RenderNestedCellHtml, RendersListOfStructAsSpreadsheet) {
  const auto html = RenderNestedCellHtml(
      R"([{"id":10,"name":"A"},{"id":20,"name":"B"}])");
  EXPECT_NE(html.find("<thead>"), std::string::npos);
  EXPECT_NE(html.find("<th>id</th>"), std::string::npos);
  EXPECT_NE(html.find("<th>name</th>"), std::string::npos);
  EXPECT_NE(html.find("<td>10</td>"), std::string::npos);
  EXPECT_NE(html.find("<td>A</td>"), std::string::npos);
  EXPECT_NE(html.find("<td>20</td>"), std::string::npos);
  EXPECT_NE(html.find("<td>B</td>"), std::string::npos);
}

TEST(RenderNestedCellHtml, RendersElementMissingAColumnAsEmptyCell) {
  const auto html = RenderNestedCellHtml(R"([{"id":1},{"id":2,"name":"B"}])");
  EXPECT_NE(html.find("<th>id</th>"), std::string::npos);
  EXPECT_NE(html.find("<th>name</th>"), std::string::npos);
  EXPECT_NE(html.find("<td></td>"), std::string::npos);
}

TEST(RenderNestedCellHtml, RendersEmptyListAsNote) {
  const auto html = RenderNestedCellHtml("[]");
  EXPECT_NE(html.find("class=\"note\""), std::string::npos);
  EXPECT_EQ(html.find("<table"), std::string::npos);
}

TEST(RenderNestedCellHtml, RendersNullStructAsLiteralNull) {
  EXPECT_EQ(RenderNestedCellHtml("null"), "null");
}

TEST(RenderNestedCellHtml, EscapesLeafValues) {
  const auto html = RenderNestedCellHtml(R"({"name":"<b>&\"'"})");
  EXPECT_EQ(html.find("<b>"), std::string::npos);
  EXPECT_NE(html.find("&lt;"), std::string::npos);
}

TEST(RenderNestedCellHtml, FallsBackToPreformattedTextOnInvalidJson) {
  const auto html = RenderNestedCellHtml("not json");
  EXPECT_NE(html.find("<pre>"), std::string::npos);
  EXPECT_NE(html.find("not json"), std::string::npos);
}

} // namespace
