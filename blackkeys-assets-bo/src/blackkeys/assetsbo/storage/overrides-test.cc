#include "blackkeys/assetsbo/storage/overrides.hpp"

#include <gtest/gtest.h>

using blackkeys::assetsbo::storage::BrandOverrides;
using blackkeys::assetsbo::storage::ParseOverrides;
using blackkeys::assetsbo::storage::SerializeOverrides;

TEST(Overrides, EmptyBytesParseToEmptyMap) {
  const auto outcome = ParseOverrides("");
  EXPECT_TRUE(outcome.error.empty());
  EXPECT_TRUE(outcome.overrides.empty());
}

TEST(Overrides, WhitespaceOnlyParsesToEmptyMap) {
  const auto outcome = ParseOverrides("   \n\t");
  EXPECT_TRUE(outcome.error.empty());
  EXPECT_TRUE(outcome.overrides.empty());
}

TEST(Overrides, MalformedJsonReportsError) {
  const auto outcome = ParseOverrides("not json");
  EXPECT_FALSE(outcome.error.empty());
}

TEST(Overrides, RoundTripsThroughSerialize) {
  BrandOverrides overrides;
  overrides["adidas"] = {{"phone", "555-0100"}, {"isActive", "false"}};
  overrides["kfc"] = {{"description", "Updated description"}};

  const auto bytes = SerializeOverrides(overrides);
  const auto outcome = ParseOverrides(bytes);

  ASSERT_TRUE(outcome.error.empty()) << outcome.error;
  ASSERT_EQ(outcome.overrides.size(), 2u);
  EXPECT_EQ(outcome.overrides.at("adidas").at("phone"), "555-0100");
  EXPECT_EQ(outcome.overrides.at("adidas").at("isActive"), "false");
  EXPECT_EQ(outcome.overrides.at("kfc").at("description"),
           "Updated description");
}
