# syntax=docker/dockerfile:1.7

ARG DROGON_VERSION=1.9.13
ARG AWS_SDK_CPP_VERSION=1.11.885
ARG BUILD_JOBS=8

FROM cgr.dev/chainguard/wolfi-base:latest AS deps

ARG BUILD_JOBS

ENV CMAKE_BUILD_PARALLEL_LEVEL=${BUILD_JOBS} \
    CMAKE_PREFIX_PATH=/usr/local \
    LD_LIBRARY_PATH=/usr/local/lib \
    PATH=/usr/lib/ninja-build/bin:${PATH}

RUN apk add --no-cache \
    apache-arrow-dev \
    aws-c-auth-dev \
    aws-c-cal-dev \
    aws-c-common-dev \
    aws-c-compression-dev \
    aws-c-event-stream-dev \
    aws-c-http-dev \
    aws-c-io-dev \
    aws-c-mqtt-dev \
    aws-c-s3-dev \
    aws-c-sdkutils-dev \
    aws-crt-cpp-dev \
    build-base \
    c-ares-dev \
    cmake \
    curl-dev \
    git \
    jsoncpp-dev \
    ldd-check \
    ninja-build \
    openssl-4.0-dev \
    s2n-tls-dev \
    thrift-dev \
    util-linux-dev \
    zlib-dev

WORKDIR /tmp/deps

ARG DROGON_VERSION

RUN git clone --depth 1 --branch v${DROGON_VERSION} --recurse-submodules --shallow-submodules \
      https://github.com/drogonframework/drogon.git \
    && cmake -S drogon -B drogon/build -GNinja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DBUILD_SHARED_LIBS=ON \
      -DTRANTOR_USE_TLS=none \
      -DBUILD_CTL=ON \
      -DBUILD_EXAMPLES=OFF \
      -DBUILD_TESTING=OFF \
      -DBUILD_DOC=OFF \
      -DBUILD_ORM=OFF \
      -DBUILD_BROTLI=OFF \
      -DBUILD_YAML_CONFIG=OFF \
      -DUSE_SUBMODULE=ON \
    && cmake --build drogon/build --parallel "${BUILD_JOBS}" --target install \
    && rm -rf drogon

ARG AWS_SDK_CPP_VERSION

RUN git clone --depth 1 --branch ${AWS_SDK_CPP_VERSION} https://github.com/aws/aws-sdk-cpp.git \
    && cmake -S aws-sdk-cpp -B aws-sdk-cpp/build -GNinja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DBUILD_SHARED_LIBS=ON \
      -DBUILD_ONLY=s3 \
      -DBUILD_DEPS=OFF \
      -DENABLE_TESTING=OFF \
      -DAUTORUN_UNIT_TESTS=OFF \
      -DAWS_SDK_WARNINGS_ARE_ERRORS=OFF \
    && cmake --build aws-sdk-cpp/build --parallel "${BUILD_JOBS}" --target install \
    && rm -rf aws-sdk-cpp

FROM deps AS build

ARG BUILD_JOBS

WORKDIR /src

COPY CMakeLists.txt ./
COPY src ./src

RUN cmake -S . -B build -GNinja \
      -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --parallel "${BUILD_JOBS}"

RUN mkdir -p /out \
    && ldd build/bin/blackkeys-assets-bo \
       | sed -nE 's#^[[:space:]]*([^[:space:]]+)[[:space:]]=>[[:space:]]*(/[^[:space:]]+).*#\1|\2#p; s#^[[:space:]]*(/[^[:space:]]+)[[:space:]].*#\1|\1#p' \
       | sort -u > /tmp/libs.txt \
    && [ -s /tmp/libs.txt ] \
    && while IFS='|' read -r name path; do \
         real="$(realpath "$path")" \
         && mkdir -p "/out$(dirname "$real")" \
         && cp -Lf "$real" "/out$real" \
         && base="$(basename "$name")" \
         && [ "$base" = "$(basename "$real")" ] \
         || ln -sf "$(basename "$real")" "/out$(dirname "$real")/$base"; \
       done < /tmp/libs.txt

RUN mkdir -p /out/app/uploads/tmp \
    && chown -R 65532:65532 /out/app

FROM quay.io/prometheus/node-exporter:v1.11.0 AS node-exporter

FROM cgr.dev/chainguard/static:latest

ENV LD_LIBRARY_PATH=/usr/local/lib \
    NODE_EXPORTER_PATH=/usr/bin/node_exporter

COPY --from=build /out/ /
COPY --from=build --chown=65532:65532 /src/build/bin/blackkeys-assets-bo /usr/local/bin/blackkeys-assets-bo
COPY --from=node-exporter --chown=65532:65532 /bin/node_exporter /usr/bin/node_exporter

USER 65532:65532

WORKDIR /app

EXPOSE 8000 9100

ENTRYPOINT ["/usr/local/bin/blackkeys-assets-bo"]
CMD ["--bind=::", "--port=8000"]
