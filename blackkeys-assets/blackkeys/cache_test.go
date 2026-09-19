package blackkeys

import (
	"errors"
	"net"
	"testing"

	"github.com/bradfitz/gomemcache/memcache"
)

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
