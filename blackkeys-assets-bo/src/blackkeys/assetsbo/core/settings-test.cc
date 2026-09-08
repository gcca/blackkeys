#include <cstdlib>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include "blackkeys/assetsbo/core/settings.hpp"

namespace {

class EnvGuard {
public:
  EnvGuard() {
    Remember("AWS_ACCESS_KEY_ID");
    Remember("AWS_SECRET_ACCESS_KEY");
    Remember("AWS_REGION");
    Remember("AWS_ENDPOINT_URL_S3");
    Remember("BUCKET_NAME");
    Remember("NODE_EXPORTER_PATH");
  }

  ~EnvGuard() {
    for (const auto &[name, value] : saved_) {
      if (value) {
        setenv(name.c_str(), value->c_str(), 1);
      } else {
        unsetenv(name.c_str());
      }
    }
  }

  void Set(const char *name, const char *value) { setenv(name, value, 1); }

  void Unset(const char *name) { unsetenv(name); }

  void SetRequired() {
    Set("AWS_ACCESS_KEY_ID", "test-id");
    Set("AWS_SECRET_ACCESS_KEY", "test-secret");
    Set("AWS_REGION", "auto");
  }

private:
  void Remember(const char *name) {
    const char *value = std::getenv(name);
    saved_.emplace_back(name, value == nullptr
                                  ? std::nullopt
                                  : std::optional<std::string>(value));
    unsetenv(name);
  }

  std::vector<std::pair<std::string, std::optional<std::string>>> saved_;
};

} // namespace

TEST(Settings, MissingAccessKey) {
  EnvGuard env;
  env.SetRequired();
  env.Unset("AWS_ACCESS_KEY_ID");
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  EXPECT_FALSE(loaded.ok);
  EXPECT_NE(loaded.error.find("AWS_ACCESS_KEY_ID"), std::string::npos);
}

TEST(Settings, MissingSecret) {
  EnvGuard env;
  env.SetRequired();
  env.Unset("AWS_SECRET_ACCESS_KEY");
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  EXPECT_FALSE(loaded.ok);
  EXPECT_NE(loaded.error.find("AWS_SECRET_ACCESS_KEY"), std::string::npos);
}

TEST(Settings, MissingRegion) {
  EnvGuard env;
  env.SetRequired();
  env.Unset("AWS_REGION");
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  EXPECT_FALSE(loaded.ok);
  EXPECT_NE(loaded.error.find("AWS_REGION"), std::string::npos);
}

TEST(Settings, DefaultsBucketAndKeepsRegion) {
  EnvGuard env;
  env.SetRequired();
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  ASSERT_TRUE(loaded.ok) << loaded.error;
  EXPECT_EQ(loaded.settings.bucket_name, "blackkeys-assets");
  EXPECT_EQ(loaded.settings.region, "auto");
  EXPECT_FALSE(loaded.settings.endpoint.overridden);
  EXPECT_TRUE(loaded.settings.access_key_id == "test-id");
  EXPECT_TRUE(loaded.settings.secret_access_key == "test-secret");
  EXPECT_TRUE(loaded.settings.node_exporter_path.empty());
}

TEST(Settings, NodeExporterPathOverride) {
  EnvGuard env;
  env.SetRequired();
  env.Set("NODE_EXPORTER_PATH", "/usr/bin/node_exporter");
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  ASSERT_TRUE(loaded.ok) << loaded.error;
  EXPECT_EQ(loaded.settings.node_exporter_path, "/usr/bin/node_exporter");
}

TEST(Settings, BucketOverride) {
  EnvGuard env;
  env.SetRequired();
  env.Set("BUCKET_NAME", "other-bucket");
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  ASSERT_TRUE(loaded.ok) << loaded.error;
  EXPECT_EQ(loaded.settings.bucket_name, "other-bucket");
}

TEST(Settings, HttpEndpoint) {
  EnvGuard env;
  env.SetRequired();
  env.Set("AWS_ENDPOINT_URL_S3", "http://127.0.0.1:9000");
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  ASSERT_TRUE(loaded.ok) << loaded.error;
  EXPECT_TRUE(loaded.settings.endpoint.overridden);
  EXPECT_FALSE(loaded.settings.endpoint.https);
  EXPECT_EQ(loaded.settings.endpoint.host, "127.0.0.1:9000");
}

TEST(Settings, HttpsEndpointStripsSlash) {
  EnvGuard env;
  env.SetRequired();
  env.Set("AWS_ENDPOINT_URL_S3", "https://fly.storage.tigris.dev/");
  const auto loaded = blackkeys::assetsbo::core::LoadSettings();
  ASSERT_TRUE(loaded.ok) << loaded.error;
  EXPECT_TRUE(loaded.settings.endpoint.https);
  EXPECT_EQ(loaded.settings.endpoint.host, "fly.storage.tigris.dev");
}

TEST(Settings, RejectsUserInfoAndPath) {
  EnvGuard env;
  env.SetRequired();
  env.Set("AWS_ENDPOINT_URL_S3", "https://user:secret@example.test");
  auto loaded = blackkeys::assetsbo::core::LoadSettings();
  EXPECT_FALSE(loaded.ok);

  env.Set("AWS_ENDPOINT_URL_S3", "https://example.test/bucket");
  loaded = blackkeys::assetsbo::core::LoadSettings();
  EXPECT_FALSE(loaded.ok);
  EXPECT_NE(loaded.error.find("path"), std::string::npos);
}
