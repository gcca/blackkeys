# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=cgr.dev/chainguard/go:latest-dev

FROM ${BASE_IMAGE} AS deps

ARG MODULE=github.com/plaza-san-miguel/blackkeys/blackkeys-assets

RUN apk add --no-cache protobuf-29.5-protoc

# Inherited by the app builder: the GOCACHE below only hits when these match.
ENV CGO_ENABLED=0 \
    GOFLAGS=-trimpath \
    PATH="/opt/protoc/bin:${PATH}"

WORKDIR /work

COPY go.mod go.sum ./

RUN go mod download \
    && go build -o /opt/protoc/bin/ \
        google.golang.org/protobuf/cmd/protoc-gen-go \
        google.golang.org/grpc/cmd/protoc-gen-go-grpc

# Warm GOCACHE with every dependency package; the source is discarded.
RUN --mount=type=bind,rw,target=/warm \
    cd /warm \
    && protoc -I protos \
        --go_out=. --go_opt=module=$MODULE \
        --go-grpc_out=. --go-grpc_opt=module=$MODULE \
        protos/v1/messages.proto protos/v1/service.proto \
    && go build -ldflags="-s -w" -o /dev/null .
