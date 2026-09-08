#include <gtest/gtest.h>

#include "blackkeys/assetsbo/storage/listing.hpp"

TEST(Segment, RejectsEmptyDotAndSlash) {
  EXPECT_TRUE(blackkeys::assetsbo::storage::RejectSegment("", "id").has_value());
  EXPECT_TRUE(blackkeys::assetsbo::storage::RejectSegment(".", "id").has_value());
  EXPECT_TRUE(blackkeys::assetsbo::storage::RejectSegment("..", "id").has_value());
  EXPECT_TRUE(blackkeys::assetsbo::storage::RejectSegment("a/b", "id").has_value());
  EXPECT_TRUE(blackkeys::assetsbo::storage::RejectSegment("a\\b", "id").has_value());
  EXPECT_TRUE(blackkeys::assetsbo::storage::RejectSegment("a\nb", "id").has_value());
  EXPECT_FALSE(blackkeys::assetsbo::storage::RejectSegment("42", "id").has_value());
  EXPECT_FALSE(blackkeys::assetsbo::storage::RejectSegment("ADIDAS", "name").has_value());
}
