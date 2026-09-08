package core

import (
	"os"
	"reflect"
	"testing"
)

func TestSettingsFromEnvReplication(t *testing.T) {
	t.Setenv("AWS_ACCESS_KEY_ID", "test-id")
	t.Setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
	t.Setenv("AWS_REGION", "test-region")
	t.Setenv("BUCKET_NAME", "")

	for _, tc := range []struct {
		name    string
		value   string
		want    int
		wantErr bool
	}{
		{"default empty", "", ReplicationDefault, false},
		{"override", "3", 3, false},
		{"zero", "0", 0, false},
		{"negative", "-1", 0, true},
		{"not integer", "abc", 0, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("REPLICATION", tc.value)
			settings, err := SettingsFromEnv()
			if tc.wantErr {
				if err == nil {
					t.Fatal("SettingsFromEnv: want error")
				}
				return
			}
			if err != nil {
				t.Fatalf("SettingsFromEnv: %v", err)
			}
			if settings.Replication != tc.want {
				t.Errorf("Replication: got %d, want %d", settings.Replication, tc.want)
			}
		})
	}
}

func TestSettingsFromEnvRegion(t *testing.T) {
	t.Setenv("AWS_ACCESS_KEY_ID", "test-id")
	t.Setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
	t.Setenv("BUCKET_NAME", "")

	for _, tc := range []struct {
		name    string
		value   string
		want    string
		wantErr bool
	}{
		{"empty", "", "", true},
		{"set", "us-east-1", "us-east-1", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("AWS_REGION", tc.value)
			settings, err := SettingsFromEnv()
			if tc.wantErr {
				if err == nil {
					t.Fatal("SettingsFromEnv: want error")
				}
				return
			}
			if err != nil {
				t.Fatalf("SettingsFromEnv: %v", err)
			}
			if settings.AWSRegion != tc.want {
				t.Errorf("AWSRegion: got %q, want %q", settings.AWSRegion, tc.want)
			}
		})
	}
}

func TestSettingsFromEnvEndpointURL(t *testing.T) {
	t.Setenv("AWS_ACCESS_KEY_ID", "test-id")
	t.Setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
	t.Setenv("AWS_REGION", "test-region")
	t.Setenv("BUCKET_NAME", "")

	for _, tc := range []struct {
		name  string
		value string
		want  string
	}{
		{"unset", "", ""},
		{"override", "http://127.0.0.1:9000", "http://127.0.0.1:9000"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("AWS_ENDPOINT_URL_S3", tc.value)
			settings, err := SettingsFromEnv()
			if err != nil {
				t.Fatalf("SettingsFromEnv: %v", err)
			}
			if settings.AWSEndpointURL != tc.want {
				t.Errorf("AWSEndpointURL: got %q, want %q", settings.AWSEndpointURL, tc.want)
			}
		})
	}
}

func TestSettingsFromEnvCacheNodes(t *testing.T) {
	t.Setenv("AWS_ACCESS_KEY_ID", "test-id")
	t.Setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
	t.Setenv("AWS_REGION", "test-region")
	t.Setenv("REPLICATION", "")
	t.Setenv("BUCKET_NAME", "")

	for _, tc := range []struct {
		name    string
		value   string
		want    []string
		wantErr bool
		unset   bool
	}{
		{"absent", "", nil, false, true},
		{"trimmed nodes", " memcached1:11211, memcached2:11211 ", []string{"memcached1:11211", "memcached2:11211"}, false, false},
		{"empty node", "memcached1:11211, ", nil, true, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if tc.unset {
				value, exists := os.LookupEnv("CACHE_NODES")
				if err := os.Unsetenv("CACHE_NODES"); err != nil {
					t.Fatalf("Unsetenv: %v", err)
				}
				t.Cleanup(func() {
					if exists {
						_ = os.Setenv("CACHE_NODES", value)
						return
					}
					_ = os.Unsetenv("CACHE_NODES")
				})
			} else {
				t.Setenv("CACHE_NODES", tc.value)
			}
			settings, err := SettingsFromEnv()
			if tc.wantErr {
				if err == nil {
					t.Fatal("SettingsFromEnv: want error")
				}
				return
			}
			if err != nil {
				t.Fatalf("SettingsFromEnv: %v", err)
			}
			if !reflect.DeepEqual(settings.CacheNodes, tc.want) {
				t.Errorf("CacheNodes: got %v, want %v", settings.CacheNodes, tc.want)
			}
		})
	}
}
