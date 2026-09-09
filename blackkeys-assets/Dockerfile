FROM cgr.dev/chainguard/rust:latest-dev AS builder

WORKDIR /work

COPY --chown=65532:65532 Cargo.toml Cargo.lock ./
COPY --chown=65532:65532 src/ ./src/

RUN cargo rustc --locked --release -- -C target-feature=+crt-static \
    && ! readelf -lW target/release/blackkeys-assets | grep -q INTERP \
    && ! readelf -dW target/release/blackkeys-assets | grep -q NEEDED

FROM cgr.dev/chainguard/static:latest

ENV ROCKET_ADDRESS=0.0.0.0 \
    ROCKET_PORT=8000

COPY --from=builder --chown=65532:65532 /work/target/release/blackkeys-assets /usr/local/bin/blackkeys-assets

USER 65532:65532

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/blackkeys-assets"]
