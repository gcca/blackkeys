#!/bin/sh
set -eu

node_exporter --web.listen-address=0.0.0.0:9100 &
memcached_exporter --memcached.address=127.0.0.1:11211 --web.listen-address=0.0.0.0:9150 &

if [ $# -eq 0 ] || { [ $# -eq 1 ] && [ "$1" = "memcached" ]; }; then
  set -- memcached \
    --listen=::,0.0.0.0 \
    --memory-limit=768 \
    --max-item-size=11m \
    --conn-limit=1024 \
    --threads=1 \
    --udp-port=0
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
