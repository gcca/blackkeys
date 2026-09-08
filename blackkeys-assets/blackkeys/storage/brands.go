package storage

import (
	"context"
	"errors"
	"fmt"
	"io"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"

	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/core"
)

const brandsObjectKey = "brands.parquet"

// ErrImageNotFound is returned by FetchImage when the requested key does not
// exist in the bucket, distinguishing a missing image from any other S3 or
// network failure.
var ErrImageNotFound = errors.New("image not found")

// NewS3Client builds the S3 client shared by every direct-object fetch in
// this package (the brands.parquet snapshot and per-brand images), applying
// the same endpoint-override/path-style rule in both cases.
func NewS3Client(ctx context.Context, settings core.Settings) (*s3.Client, error) {
	cfg, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(settings.AWSRegion),
		config.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(settings.AWSAccessKeyID, settings.AWSSecretAccessKey, ""),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("aws config: %w", err)
	}

	return s3.NewFromConfig(cfg, func(o *s3.Options) {
		if settings.AWSEndpointURL != "" {
			o.BaseEndpoint = aws.String(settings.AWSEndpointURL)
			o.UsePathStyle = true
		}
	}), nil
}

func FetchBrandsSnapshot(ctx context.Context, settings core.Settings) ([]byte, error) {
	client, err := NewS3Client(ctx, settings)
	if err != nil {
		return nil, err
	}

	output, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(settings.BucketName),
		Key:    aws.String(brandsObjectKey),
	})
	if err != nil {
		return nil, fmt.Errorf("get object %s/%s: %w", settings.BucketName, brandsObjectKey, err)
	}
	defer output.Body.Close()

	data, err := io.ReadAll(output.Body)
	if err != nil {
		return nil, fmt.Errorf("read object body: %w", err)
	}
	return data, nil
}

const defaultImageContentType = "image/png"

// FetchImage fetches a single object from bucket/key using an already
// constructed client (see NewS3Client), for repeated per-request reads (e.g.
// brand logo/picture bytes) where building a new client every call would be
// wasteful. A missing object returns ErrImageNotFound.
func FetchImage(ctx context.Context, client *s3.Client, bucket, key string) (data []byte, contentType string, err error) {
	output, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		var noSuchKey *types.NoSuchKey
		if errors.As(err, &noSuchKey) {
			return nil, "", ErrImageNotFound
		}
		return nil, "", fmt.Errorf("get object %s/%s: %w", bucket, key, err)
	}
	defer output.Body.Close()

	data, err = io.ReadAll(output.Body)
	if err != nil {
		return nil, "", fmt.Errorf("read object body: %w", err)
	}

	contentType = aws.ToString(output.ContentType)
	if contentType == "" {
		contentType = defaultImageContentType
	}
	return data, contentType, nil
}
