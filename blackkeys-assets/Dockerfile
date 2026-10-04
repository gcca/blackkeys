# syntax=docker/dockerfile:1.7

ARG DEPS_IMAGE=ghcr.io/gcca/blackkeys:assets-deps
ARG NODE_EXPORTER_IMAGE=quay.io/prometheus/node-exporter:v1.11.0
ARG STATIC_IMAGE=cgr.dev/chainguard/static:latest

FROM ${DEPS_IMAGE} AS builder

ARG MODULE=github.com/plaza-san-miguel/blackkeys/blackkeys-assets

WORKDIR /work

COPY --chown=65532:65532 go.mod go.sum ./

RUN go mod download

COPY --chown=65532:65532 protos/ ./protos/
COPY --chown=65532:65532 blackkeys/ ./blackkeys/
COPY --chown=65532:65532 main.go ./

RUN protoc -I protos \
        --go_out=. --go_opt=module=$MODULE \
        --go-grpc_out=. --go-grpc_opt=module=$MODULE \
        protos/v1/messages.proto protos/v1/service.proto

RUN go build -ldflags="-s -w" -o blackkeys-assets . \
    && ! readelf -lW blackkeys-assets | grep -q INTERP \
    && ! readelf -dW blackkeys-assets | grep -q NEEDED

FROM ${NODE_EXPORTER_IMAGE} AS node-exporter

FROM ${STATIC_IMAGE}

ENV GRPC_ADDRESS=0.0.0.0 \
    GRPC_PORT=50051 \
    NODE_EXPORTER_PATH=/usr/bin/node_exporter

COPY --from=builder --chown=65532:65532 /work/blackkeys-assets /usr/local/bin/blackkeys-assets
COPY --from=node-exporter --chown=65532:65532 /bin/node_exporter /usr/bin/node_exporter

USER 65532:65532

EXPOSE 50051 9100

ENTRYPOINT ["/usr/local/bin/blackkeys-assets"]
