package storage

import (
	"context"
	"fmt"
	"io"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	tigris "github.com/tigrisdata/storage-go"

	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/core"
)

const storesObjectKey = "stores.parquet"

func FetchStoresSnapshot(ctx context.Context, settings core.Settings) ([]byte, error) {
	client, err := tigris.New(ctx, tigris.WithAccessKeypair(settings.AWSAccessKeyID, settings.AWSSecretAccessKey))
	if err != nil {
		return nil, fmt.Errorf("tigris client: %w", err)
	}

	output, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(settings.BucketName),
		Key:    aws.String(storesObjectKey),
	})
	if err != nil {
		return nil, fmt.Errorf("get object %s/%s: %w", settings.BucketName, storesObjectKey, err)
	}
	defer output.Body.Close()

	data, err := io.ReadAll(output.Body)
	if err != nil {
		return nil, fmt.Errorf("read object body: %w", err)
	}
	return data, nil
}
