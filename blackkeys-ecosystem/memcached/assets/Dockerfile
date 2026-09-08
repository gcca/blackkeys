# syntax=docker/dockerfile:1

FROM quay.io/prometheus/node-exporter:v1.11.0 AS node-exporter
FROM prom/memcached-exporter:v0.17.0 AS memcached-exporter

FROM memcached:1.6-alpine

COPY --from=node-exporter /bin/node_exporter /usr/local/bin/node_exporter
COPY --from=memcached-exporter /bin/memcached_exporter /usr/local/bin/memcached_exporter
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 11211 9100 9150

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["memcached"]
