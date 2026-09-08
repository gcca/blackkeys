package blackkeys

import (
	"errors"
	"net"
	"testing"

	"github.com/bradfitz/gomemcache/memcache"
)

type fakeNodeClient struct {
	getItem  *memcache.Item
	getErr   error
	setErr   error
	getCalls int
	setCalls int
}

func (c *fakeNodeClient) Get(string) (*memcache.Item, error) {
	c.getCalls++
	return c.getItem, c.getErr
}

func (c *fakeNodeClient) Set(*memcache.Item) error {
	c.setCalls++
	return c.setErr
}

func newTestReplicaClient(t *testing.T, replication int) (*ReplicaClient, map[string]*fakeNodeClient) {
	t.Helper()
	clients := map[string]*fakeNodeClient{
		"127.0.0.1:11211": {},
		"127.0.0.1:11212": {},
		"127.0.0.1:11213": {},
	}
	client, err := newReplicaClient(replication, []string{"127.0.0.1:11211", "127.0.0.1:11212", "127.0.0.1:11213"}, func(node string) memcacheClient {
		return clients[node]
	})
	if err != nil {
		t.Fatalf("newReplicaClient: %v", err)
	}
	return client, clients
}

func TestPickServerIsDeterministic(t *testing.T) {
	ss, err := NewSelector("127.0.0.1:11211", "127.0.0.1:11212")
	if err != nil {
		t.Fatalf("NewSelector: %v", err)
	}
	first, err := ss.PickServer("sticky-key")
	if err != nil {
		t.Fatalf("PickServer: %v", err)
	}
	for i := 0; i < 8; i++ {
		got, err := ss.PickServer("sticky-key")
		if err != nil {
			t.Fatalf("PickServer: %v", err)
		}
		if got.String() != first.String() {
			t.Fatalf("PickServer: got %s, want %s", got, first)
		}
	}
}

func TestEachVisitsBothNodes(t *testing.T) {
	ss, err := NewSelector("127.0.0.1:11211", "127.0.0.1:11212")
	if err != nil {
		t.Fatalf("NewSelector: %v", err)
	}
	seen := map[string]int{}
	if err := ss.Each(func(addr net.Addr) error {
		seen[addr.String()]++
		return nil
	}); err != nil {
		t.Fatalf("Each: %v", err)
	}
	if len(seen) != 2 {
		t.Fatalf("Each visited %d addrs, want 2: %v", len(seen), seen)
	}
	for _, want := range []string{"127.0.0.1:11211", "127.0.0.1:11212"} {
		if seen[want] != 1 {
			t.Errorf("Each %s: got %d, want 1", want, seen[want])
		}
	}
}

func TestNewSelectorBadAddress(t *testing.T) {
	_, err := NewSelector("not a host")
	if err == nil {
		t.Fatal("NewSelector: want error")
	}
}

func TestEmptySelectorPickServer(t *testing.T) {
	ss, err := NewSelector()
	if err != nil {
		t.Fatalf("NewSelector: %v", err)
	}
	_, err = ss.PickServer("k")
	if !errors.Is(err, memcache.ErrNoServers) {
		t.Errorf("PickServer empty: got %v, want ErrNoServers", err)
	}
}

func TestNewClient(t *testing.T) {
	client, err := NewClient("127.0.0.1:11211")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if client == nil {
		t.Fatal("NewClient: got nil client")
	}
}

func TestReplicaClientWritesSelectedNodes(t *testing.T) {
	client, clients := newTestReplicaClient(t, 1)
	key := "replicated-key"
	selected := client.selector.nodesFor(key, 2)
	if len(selected) != 2 {
		t.Fatalf("selected nodes: got %v, want two nodes", selected)
	}

	if err := client.Set(&memcache.Item{Key: key, Value: []byte("value")}); err != nil {
		t.Fatalf("Set: %v", err)
	}
	for node, fake := range clients {
		want := 0
		for _, selectedNode := range selected {
			if node == selectedNode {
				want = 1
			}
		}
		if fake.setCalls != want {
			t.Errorf("Set calls for %s: got %d, want %d", node, fake.setCalls, want)
		}
	}
}

func TestReplicaClientContinuesWritesAfterFailure(t *testing.T) {
	client, clients := newTestReplicaClient(t, 1)
	key := "replicated-key"
	selected := client.selector.nodesFor(key, 2)
	clients[selected[0]].setErr = errors.New("write")

	if err := client.Set(&memcache.Item{Key: key, Value: []byte("value")}); err == nil {
		t.Fatal("Set: want error")
	}
	for _, node := range selected {
		if clients[node].setCalls != 1 {
			t.Errorf("Set calls for %s: got %d, want 1", node, clients[node].setCalls)
		}
	}
}

func TestReplicaClientFallsBackOnPrimaryMissOrError(t *testing.T) {
	for _, primaryErr := range []error{memcache.ErrCacheMiss, errors.New("read")} {
		t.Run(primaryErr.Error(), func(t *testing.T) {
			client, clients := newTestReplicaClient(t, 1)
			key := "replicated-key"
			selected := client.selector.nodesFor(key, 2)
			clients[selected[0]].getErr = primaryErr
			clients[selected[1]].getItem = &memcache.Item{Key: key, Value: []byte("value")}

			item, err := client.Get(key)
			if err != nil {
				t.Fatalf("Get: %v", err)
			}
			if string(item.Value) != "value" {
				t.Errorf("Get value: got %q, want value", item.Value)
			}
			for index, node := range selected {
				if clients[node].getCalls != 1 {
					t.Errorf("Get calls for selected node %d (%s): got %d, want 1", index, node, clients[node].getCalls)
				}
			}
			for node, fake := range clients {
				if node != selected[0] && node != selected[1] && fake.getCalls != 0 {
					t.Errorf("Get calls for unselected node %s: got %d, want 0", node, fake.getCalls)
				}
			}
		})
	}
}

func TestReplicaClientReplicationIsExtraReplicasBeyondPrimary(t *testing.T) {
	for _, tc := range []struct {
		name        string
		replication int
		wantNodes   int
	}{
		{"zero extra replicas targets primary only", 0, 1},
		{"one extra replica targets primary and another", 1, 2},
		{"two extra replicas targets all configured nodes", 2, 3},
	} {
		t.Run(tc.name, func(t *testing.T) {
			client, clients := newTestReplicaClient(t, tc.replication)
			key := "replicated-key"

			if err := client.Set(&memcache.Item{Key: key, Value: []byte("value")}); err != nil {
				t.Fatalf("Set: %v", err)
			}

			written := 0
			for _, fake := range clients {
				if fake.setCalls > 0 {
					written++
				}
			}
			if written != tc.wantNodes {
				t.Errorf("nodes written: got %d, want %d", written, tc.wantNodes)
			}
		})
	}
}

func TestNewReplicaClientNegativeReplicationFloorsToPrimaryOnly(t *testing.T) {
	client, clients := newTestReplicaClient(t, -1)
	key := "replicated-key"

	if err := client.Set(&memcache.Item{Key: key, Value: []byte("value")}); err != nil {
		t.Fatalf("Set: %v", err)
	}

	written := 0
	for _, fake := range clients {
		if fake.setCalls > 0 {
			written++
		}
	}
	if written != 1 {
		t.Errorf("nodes written: got %d, want 1 (primary only)", written)
	}
}

func TestEachStopsOnError(t *testing.T) {
	ss, err := NewSelector("127.0.0.1:11211", "127.0.0.1:11212")
	if err != nil {
		t.Fatalf("NewSelector: %v", err)
	}
	want := errors.New("stop")
	got := ss.Each(func(net.Addr) error { return want })
	if !errors.Is(got, want) {
		t.Errorf("Each: got %v, want %v", got, want)
	}
}
