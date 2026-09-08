package core

import "testing"

func TestGetEmpty(t *testing.T) {
	r := New(4)
	if got, ok := r.Get("anything"); ok || got != "" {
		t.Errorf("Get empty: got %q, %v; want \"\", false", got, ok)
	}
}

func TestGetNEmptyAndNonPositive(t *testing.T) {
	r := New(4)
	if got := r.GetN("anything", 1); got != nil {
		t.Errorf("GetN empty: got %v, want nil", got)
	}
	r.Add("alpha")
	for _, n := range []int{0, -1} {
		if got := r.GetN("anything", n); got != nil {
			t.Errorf("GetN n=%d: got %v, want nil", n, got)
		}
	}
}

func TestOneNodeAlwaysWins(t *testing.T) {
	r := New(4)
	r.Add("alpha")
	for _, key := range []string{"a", "b", "c", "key-1", "key-2"} {
		got, ok := r.Get(key)
		if !ok || got != "alpha" {
			t.Errorf("Get(%q): got %q, %v; want alpha, true", key, got, ok)
		}
	}
}

func TestGetIsSticky(t *testing.T) {
	r := New(DefaultReplicas)
	r.Add("alpha")
	r.Add("beta")
	first, ok := r.Get("sticky-key")
	if !ok {
		t.Fatal("Get sticky-key: want true")
	}
	for i := 0; i < 8; i++ {
		got, ok := r.Get("sticky-key")
		if !ok || got != first {
			t.Fatalf("Get sticky-key: got %q, %v; want %q, true", got, ok, first)
		}
	}
}

func TestGetNStartsWithGetAndIsDeterministic(t *testing.T) {
	r := New(DefaultReplicas)
	for _, node := range []string{"alpha", "beta", "gamma"} {
		r.Add(node)
	}

	primary, ok := r.Get("replicated-key")
	if !ok {
		t.Fatal("Get replicated-key: want true")
	}
	want := r.GetN("replicated-key", 3)
	if len(want) != 3 {
		t.Fatalf("GetN length: got %d, want 3", len(want))
	}
	if want[0] != primary {
		t.Errorf("GetN primary: got %q, want %q", want[0], primary)
	}
	seen := make(map[string]struct{}, len(want))
	for _, node := range want {
		if _, exists := seen[node]; exists {
			t.Errorf("GetN returned duplicate node %q in %v", node, want)
		}
		seen[node] = struct{}{}
	}
	for i := 0; i < 8; i++ {
		got := r.GetN("replicated-key", 3)
		for index := range want {
			if got[index] != want[index] {
				t.Fatalf("GetN repeat %d: got %v, want %v", i, got, want)
			}
		}
	}
}

func TestGetNCapsAtAvailableNodes(t *testing.T) {
	r := New(DefaultReplicas)
	r.Add("alpha")
	r.Add("beta")
	got := r.GetN("key", 3)
	if len(got) != 2 {
		t.Fatalf("GetN length: got %d, want 2", len(got))
	}
	if got[0] == got[1] {
		t.Errorf("GetN: got duplicate nodes %v", got)
	}
}

func TestAddSecondNodeDoesNotMoveEveryKey(t *testing.T) {
	r := New(DefaultReplicas)
	r.Add("alpha")
	keys := []string{"k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9"}
	before := make(map[string]string, len(keys))
	for _, key := range keys {
		got, ok := r.Get(key)
		if !ok {
			t.Fatalf("Get(%q) before add: want true", key)
		}
		before[key] = got
	}
	r.Add("beta")
	stayed := 0
	for _, key := range keys {
		got, ok := r.Get(key)
		if !ok {
			t.Fatalf("Get(%q) after add: want true", key)
		}
		if got == before[key] {
			stayed++
		}
	}
	if stayed == 0 {
		t.Fatal("adding beta moved every key")
	}
}

func TestRemoveStopsReturningNode(t *testing.T) {
	r := New(DefaultReplicas)
	r.Add("alpha")
	r.Add("beta")
	r.Remove("beta")
	if r.Len() != 1 {
		t.Errorf("Len after Remove: got %d, want 1", r.Len())
	}
	for _, key := range []string{"a", "b", "c", "d", "e"} {
		got, ok := r.Get(key)
		if !ok || got != "alpha" {
			t.Errorf("Get(%q) after Remove: got %q, %v; want alpha, true", key, got, ok)
		}
	}
}

func TestDuplicateAddDoesNotGrowLen(t *testing.T) {
	r := New(4)
	r.Add("alpha")
	r.Add("alpha")
	if got := r.Len(); got != 1 {
		t.Errorf("Len after duplicate Add: got %d, want 1", got)
	}
}

func TestNewNonPositiveReplicasUsesDefault(t *testing.T) {
	r := New(0)
	r.Add("alpha")
	if got := r.Len(); got != 1 {
		t.Errorf("Len: got %d, want 1", got)
	}
	if _, ok := r.Get("k"); !ok {
		t.Error("Get after New(0): want true")
	}
}
