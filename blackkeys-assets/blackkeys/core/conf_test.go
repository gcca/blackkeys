package core

import "testing"

func TestSettingsFromEnvReplication(t *testing.T) {
	t.Setenv("AWS_ACCESS_KEY_ID", "test-id")
	t.Setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
	t.Setenv("BUCKET_NAME", "")

	for _, tc := range []struct {
		name    string
		value   string
		want    int
		wantErr bool
	}{
		{"default empty", "", ReplicationDefault, false},
		{"override", "3", 3, false},
		{"zero", "0", 0, true},
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
