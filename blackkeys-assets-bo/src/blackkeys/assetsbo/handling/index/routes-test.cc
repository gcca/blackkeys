#include "blackkeys/assetsbo/handling/index/routes.hpp"

#include <drogon/HttpResponse.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>

using blackkeys::assetsbo::handling::index::Index;

TEST(IndexRoutes, HomeShowsBrandsAndEvents) {
  Index controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.Home(nullptr, callback.AsStdFunction());

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k200OK);
  EXPECT_THAT(std::string(response->body()), testing::HasSubstr("href=\"/v1/brand/list\""));
  EXPECT_THAT(std::string(response->body()), testing::HasSubstr("href=\"/v1/event/list\""));
  EXPECT_THAT(std::string(response->body()), testing::HasSubstr("Home</a>"));
}

TEST(IndexRoutes, HealthcheckReturnsOk) {
  Index controller;
  testing::MockFunction<void(const drogon::HttpResponsePtr &)> callback;
  drogon::HttpResponsePtr response;
  EXPECT_CALL(callback, Call(testing::NotNull()))
      .WillOnce(testing::SaveArg<0>(&response));

  controller.Healthcheck(nullptr, callback.AsStdFunction());

  ASSERT_TRUE(response);
  EXPECT_EQ(response->statusCode(), drogon::k200OK);
}
