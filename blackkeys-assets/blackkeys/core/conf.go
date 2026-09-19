package core

import (
	"fmt"
	"os"
	"strconv"
)

const BucketNameDefault = "blackkeys-assets"
const ReplicationDefault = 1

type Settings struct {
	AWSAccessKeyID     string
	AWSSecretAccessKey string
	BucketName         string
	Replication        int
}

func SettingsFromEnv() (Settings, error) {
	awsAccessKeyID, err := readAWSAccessKeyID()
	if err != nil {
		return Settings{}, err
	}

	awsSecretAccessKey, err := readAWSSecretAccessKey()
	if err != nil {
		return Settings{}, err
	}

	replication, err := readReplication()
	if err != nil {
		return Settings{}, err
	}

	return Settings{
		AWSAccessKeyID:     awsAccessKeyID,
		AWSSecretAccessKey: awsSecretAccessKey,
		BucketName:         readBucketName(),
		Replication:        replication,
	}, nil
}

func readAWSAccessKeyID() (string, error) {
	value := os.Getenv("AWS_ACCESS_KEY_ID")
	if value == "" {
		return "", fmt.Errorf("AWS_ACCESS_KEY_ID must not be empty")
	}
	return value, nil
}

func readAWSSecretAccessKey() (string, error) {
	value := os.Getenv("AWS_SECRET_ACCESS_KEY")
	if value == "" {
		return "", fmt.Errorf("AWS_SECRET_ACCESS_KEY must not be empty")
	}
	return value, nil
}

func readBucketName() string {
	value := os.Getenv("BUCKET_NAME")
	if value == "" {
		return BucketNameDefault
	}
	return value
}

func readReplication() (int, error) {
	value := os.Getenv("REPLICATION")
	if value == "" {
		return ReplicationDefault, nil
	}
	replication, err := strconv.Atoi(value)
	if err != nil {
		return 0, fmt.Errorf("REPLICATION must be an integer")
	}
	if replication <= 0 {
		return 0, fmt.Errorf("REPLICATION must be greater than zero")
	}
	return replication, nil
}
