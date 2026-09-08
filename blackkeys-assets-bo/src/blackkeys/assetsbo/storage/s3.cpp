#include "blackkeys/assetsbo/storage/s3.hpp"

#include <memory>
#include <sstream>

#include <aws/core/auth/AWSCredentials.h>
#include <aws/core/client/ClientConfiguration.h>
#include <aws/s3/S3Client.h>
#include <aws/s3/model/DeleteObjectRequest.h>
#include <aws/s3/model/GetObjectRequest.h>
#include <aws/s3/model/PutObjectRequest.h>

namespace blackkeys::assetsbo::storage {
namespace {

std::unique_ptr<Aws::S3::S3Client> client;
std::string bucket_name;
ObjectStore *test_store = nullptr;

std::string FormatS3Error(const Aws::S3::S3Error &failure) {
  const std::string name = failure.GetExceptionName().c_str();
  const std::string message = failure.GetMessage().c_str();
  if (!name.empty() && !message.empty()) {
    return name + ": " + message;
  }
  if (!name.empty()) {
    return name;
  }
  if (!message.empty()) {
    return message;
  }
  return "S3Error";
}

} // namespace

void InitClient(const assetsbo::core::Settings &settings) {
  bucket_name = settings.bucket_name;

  Aws::S3::S3ClientConfiguration configuration;
  configuration.region = settings.region;
  configuration.disableIMDS = true;
  configuration.connectTimeoutMs = 2000;
  if (settings.endpoint.overridden) {
    configuration.endpointOverride = settings.endpoint.host;
    configuration.scheme = settings.endpoint.https ? Aws::Http::Scheme::HTTPS
                                                   : Aws::Http::Scheme::HTTP;
    configuration.useVirtualAddressing = false;
  }

  const Aws::Auth::AWSCredentials credentials(settings.access_key_id,
                                              settings.secret_access_key);
  client =
      std::make_unique<Aws::S3::S3Client>(credentials, nullptr, configuration);
}

const std::string &BucketName() { return bucket_name; }

GetOutcome GetObject(const std::string &key) {
  if (test_store) {
    return test_store->Get(key);
  }

  GetOutcome outcome;
  if (!client) {
    outcome.error = "S3Error";
    return outcome;
  }

  Aws::S3::Model::GetObjectRequest request;
  request.SetBucket(bucket_name);
  request.SetKey(key);

  auto got = client->GetObject(request);
  if (!got.IsSuccess()) {
    const auto &failure = got.GetError();
    if (std::string(failure.GetExceptionName().c_str()) == "NoSuchKey") {
      outcome.not_found = true;
      return outcome;
    }
    outcome.error = FormatS3Error(failure);
    return outcome;
  }

  auto result = got.GetResultWithOwnership();
  std::ostringstream body;
  body << result.GetBody().rdbuf();
  outcome.body = body.str();
  if (result.GetLastModified().WasParseSuccessful() &&
      result.GetLastModified().Millis() != 0) {
    outcome.last_modified = result.GetLastModified()
                                .ToGmtString(Aws::Utils::DateFormat::RFC822)
                                .c_str();
  }
  return outcome;
}

PutOutcome PutObject(const std::string &key, const std::string &body,
                     const std::string &content_type) {
  if (test_store) {
    return test_store->Put(key, body, content_type);
  }

  PutOutcome outcome;
  if (!client) {
    outcome.error = "S3Error";
    return outcome;
  }

  auto content = std::make_shared<std::stringstream>(body);

  Aws::S3::Model::PutObjectRequest request;
  request.SetBucket(bucket_name);
  request.SetKey(key);
  request.SetContentType(content_type);
  request.SetBody(content);

  auto put = client->PutObject(request);
  if (!put.IsSuccess()) {
    outcome.error = FormatS3Error(put.GetError());
  }
  return outcome;
}

DeleteOutcome DeleteObject(const std::string &key) {
  if (test_store) {
    return test_store->Delete(key);
  }

  DeleteOutcome outcome;
  if (!client) {
    outcome.error = "S3Error";
    return outcome;
  }

  Aws::S3::Model::DeleteObjectRequest request;
  request.SetBucket(bucket_name);
  request.SetKey(key);

  auto deleted = client->DeleteObject(request);
  if (!deleted.IsSuccess()) {
    outcome.error = FormatS3Error(deleted.GetError());
  }
  return outcome;
}

void SetObjectStoreForTesting(ObjectStore *store) { test_store = store; }

} // namespace blackkeys::assetsbo::storage
