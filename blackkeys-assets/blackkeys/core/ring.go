package core

import (
	"hash/crc32"
	"sort"
	"strconv"
	"sync"
)

const DefaultReplicas = 100

type vnode struct {
	hash uint32
	node string
}

type Ring struct {
	mu       sync.RWMutex
	replicas int
	vnodes   []vnode
	nodes    map[string]struct{}
}

func Hash(s string) uint32 {
	return crc32.ChecksumIEEE([]byte(s))
}

func New(replicas int) *Ring {
	if replicas <= 0 {
		replicas = DefaultReplicas
	}
	return &Ring{
		replicas: replicas,
		nodes:    make(map[string]struct{}),
	}
}

func (r *Ring) Add(node string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, exists := r.nodes[node]; exists {
		return
	}
	r.nodes[node] = struct{}{}
	for i := 0; i < r.replicas; i++ {
		r.vnodes = append(r.vnodes, vnode{
			hash: Hash(node + "#" + strconv.Itoa(i)),
			node: node,
		})
	}
	sort.Slice(r.vnodes, func(i, j int) bool {
		if r.vnodes[i].hash == r.vnodes[j].hash {
			return r.vnodes[i].node < r.vnodes[j].node
		}
		return r.vnodes[i].hash < r.vnodes[j].hash
	})
}

func (r *Ring) Remove(node string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, exists := r.nodes[node]; !exists {
		return
	}
	delete(r.nodes, node)
	kept := r.vnodes[:0]
	for _, vn := range r.vnodes {
		if vn.node != node {
			kept = append(kept, vn)
		}
	}
	r.vnodes = kept
}

func (r *Ring) Get(key string) (string, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if len(r.vnodes) == 0 {
		return "", false
	}
	h := Hash(key)
	i := sort.Search(len(r.vnodes), func(i int) bool {
		return r.vnodes[i].hash >= h
	})
	if i == len(r.vnodes) {
		i = 0
	}
	return r.vnodes[i].node, true
}

func (r *Ring) Len() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.nodes)
}
