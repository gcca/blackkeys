package core

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

const BucketNameDefault = "blackkeys-assets"
const ReplicationDefault = 0

type Settings struct {
	AWSAccessKeyID     string
	AWSSecretAccessKey string
	AWSRegion          string
	AWSEndpointURL     string
	BucketName         string
	Replication        int
	CacheNodes         []string
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

	awsRegion, err := readAWSRegion()
	if err != nil {
		return Settings{}, err
	}

	replication, err := readReplication()
	if err != nil {
		return Settings{}, err
	}

	cacheNodes, err := readCacheNodes()
	if err != nil {
		return Settings{}, err
	}

	return Settings{
		AWSAccessKeyID:     awsAccessKeyID,
		AWSSecretAccessKey: awsSecretAccessKey,
		AWSRegion:          awsRegion,
		AWSEndpointURL:     readAWSEndpointURL(),
		BucketName:         readBucketName(),
		Replication:        replication,
		CacheNodes:         cacheNodes,
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

func readAWSRegion() (string, error) {
	value := os.Getenv("AWS_REGION")
	if value == "" {
		return "", fmt.Errorf("AWS_REGION must not be empty")
	}
	return value, nil
}

func readAWSEndpointURL() string {
	return os.Getenv("AWS_ENDPOINT_URL_S3")
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
	if replication < 0 {
		return 0, fmt.Errorf("REPLICATION must not be negative")
	}
	return replication, nil
}

func readCacheNodes() ([]string, error) {
	value := os.Getenv("CACHE_NODES")
	if value == "" {
		return nil, nil
	}

	nodes := strings.Split(value, ",")
	for index, node := range nodes {
		node = strings.TrimSpace(node)
		if node == "" {
			return nil, fmt.Errorf("CACHE_NODES contains an empty node")
		}
		nodes[index] = node
	}
	return nodes, nil
}
