FROM cgr.dev/chainguard/protobuf:latest AS protoc

FROM cgr.dev/chainguard/go:latest-dev AS builder

ARG MODULE=github.com/plaza-san-miguel/blackkeys/blackkeys-assets

WORKDIR /work

COPY --from=protoc --chown=65532:65532 /usr/bin/protoc /usr/bin/protoc

COPY --chown=65532:65532 go.mod go.sum ./

RUN go mod download

COPY --chown=65532:65532 protos/ ./protos/
COPY --chown=65532:65532 blackkeys/ ./blackkeys/
COPY --chown=65532:65532 main.go ./

RUN go build -o .bin/protoc-gen-go google.golang.org/protobuf/cmd/protoc-gen-go \
    && go build -o .bin/protoc-gen-go-grpc google.golang.org/grpc/cmd/protoc-gen-go-grpc \
    && PATH="/work/.bin:$PATH" protoc -I protos \
        --go_out=. --go_opt=module=$MODULE \
        --go-grpc_out=. --go-grpc_opt=module=$MODULE \
        protos/v1/messages.proto protos/v1/service.proto

RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o blackkeys-assets . \
    && ! readelf -lW blackkeys-assets | grep -q INTERP \
    && ! readelf -dW blackkeys-assets | grep -q NEEDED

FROM cgr.dev/chainguard/static:latest

ENV GRPC_ADDRESS=0.0.0.0 \
    GRPC_PORT=50051

COPY --from=builder --chown=65532:65532 /work/blackkeys-assets /usr/local/bin/blackkeys-assets

USER 65532:65532

EXPOSE 50051

ENTRYPOINT ["/usr/local/bin/blackkeys-assets"]
