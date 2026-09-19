package blackkeys

import (
	"fmt"
	"net"

	"github.com/bradfitz/gomemcache/memcache"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/core"
)

var _ memcache.ServerSelector = (*selector)(nil)

type selector struct {
	ring   *core.Ring
	addrs  []net.Addr
	byNode map[string]net.Addr
}

func NewSelector(nodes ...string) (memcache.ServerSelector, error) {
	r := core.New(core.DefaultReplicas)
	addrs := make([]net.Addr, 0, len(nodes))
	byNode := make(map[string]net.Addr, len(nodes))
	for _, node := range nodes {
		if _, exists := byNode[node]; exists {
			continue
		}
		addr, err := net.ResolveTCPAddr("tcp", node)
		if err != nil {
			return nil, fmt.Errorf("resolve %q: %w", node, err)
		}
		r.Add(node)
		addrs = append(addrs, addr)
		byNode[node] = addr
	}
	return &selector{ring: r, addrs: addrs, byNode: byNode}, nil
}

func NewClient(nodes ...string) (*memcache.Client, error) {
	ss, err := NewSelector(nodes...)
	if err != nil {
		return nil, err
	}
	return memcache.NewFromSelector(ss), nil
}

func (s *selector) PickServer(key string) (net.Addr, error) {
	node, ok := s.ring.Get(key)
	if !ok {
		return nil, memcache.ErrNoServers
	}
	return s.byNode[node], nil
}

func (s *selector) Each(fn func(net.Addr) error) error {
	for _, addr := range s.addrs {
		if err := fn(addr); err != nil {
			return err
		}
	}
	return nil
}
