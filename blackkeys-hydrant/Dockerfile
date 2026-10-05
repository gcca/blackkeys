# syntax=docker/dockerfile:1.7

ARG C3_PLATFORM=linux/amd64
ARG DEPS_IMAGE=ghcr.io/gcca/blackkeys:hydrant-deps
ARG STATIC_IMAGE=cgr.dev/chainguard/static:latest

FROM --platform=${C3_PLATFORM} ${DEPS_IMAGE} AS build

WORKDIR /src
COPY . .

RUN mkdir -p build/generated \
    && flatc --cpp -o build/generated schemas/user_auth.fbs schemas/user_signup.fbs schemas/hydration_message.fbs \
    && clang++ -std=c++17 -Ibuild/generated -I/usr/include -c src/interop/fbufs.cpp -o build/fbufs.o

RUN cp project.linux.json project.json \
    && c3c --trust=full build blackkeys-hydrant -z -static \
    && ! readelf -lW build/blackkeys-hydrant | grep -q INTERP \
    && ! readelf -dW build/blackkeys-hydrant | grep -q NEEDED

FROM --platform=${C3_PLATFORM} ${STATIC_IMAGE}

COPY --from=build --chown=nonroot:nonroot /src/build/blackkeys-hydrant /usr/local/bin/blackkeys-hydrant

ENTRYPOINT ["/usr/local/bin/blackkeys-hydrant"]
