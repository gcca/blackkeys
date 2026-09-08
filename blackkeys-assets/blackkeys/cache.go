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
	return newSelector(nodes...)
}

func newSelector(nodes ...string) (*selector, error) {
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
	ss, err := newSelector(nodes...)
	if err != nil {
		return nil, err
	}
	return memcache.NewFromSelector(ss), nil
}

type memcacheClient interface {
	Get(string) (*memcache.Item, error)
	Set(*memcache.Item) error
}

type ReplicaClient struct {
	selector    *selector
	replication int
	clients     map[string]memcacheClient
}

func NewReplicaClient(replication int, nodes ...string) (*ReplicaClient, error) {
	return newReplicaClient(replication, nodes, func(node string) memcacheClient {
		return memcache.New(node)
	})
}

func newReplicaClient(replication int, nodes []string, newClient func(string) memcacheClient) (*ReplicaClient, error) {
	if replication < 0 {
		replication = 0
	}

	ss, err := newSelector(nodes...)
	if err != nil {
		return nil, err
	}

	clients := make(map[string]memcacheClient, len(ss.byNode))
	for node := range ss.byNode {
		clients[node] = newClient(node)
	}
	return &ReplicaClient{
		selector:    ss,
		replication: replication,
		clients:     clients,
	}, nil
}

func (s *selector) PickServer(key string) (net.Addr, error) {
	node, ok := s.ring.Get(key)
	if !ok {
		return nil, memcache.ErrNoServers
	}
	return s.byNode[node], nil
}

func (s *selector) nodesFor(key string, n int) []string {
	return s.ring.GetN(key, n)
}

func (s *selector) Each(fn func(net.Addr) error) error {
	for _, addr := range s.addrs {
		if err := fn(addr); err != nil {
			return err
		}
	}
	return nil
}

func (c *ReplicaClient) Get(key string) (*memcache.Item, error) {
	var lastErr error
	for _, node := range c.selector.nodesFor(key, c.replication+1) {
		item, err := c.clients[node].Get(key)
		if err == nil {
			return item, nil
		}
		lastErr = err
	}
	if lastErr == nil {
		return nil, memcache.ErrNoServers
	}
	return nil, lastErr
}

func (c *ReplicaClient) Set(item *memcache.Item) error {
	var firstErr error
	for _, node := range c.selector.nodesFor(item.Key, c.replication+1) {
		if err := c.clients[node].Set(item); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	return firstErr
}
