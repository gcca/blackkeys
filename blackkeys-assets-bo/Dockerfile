# syntax=docker/dockerfile:1.7

ARG DEPS_IMAGE=ghcr.io/gcca/blackkeys:assets-bo-deps
ARG NODE_EXPORTER_IMAGE=quay.io/prometheus/node-exporter:v1.11.0
ARG STATIC_IMAGE=cgr.dev/chainguard/static:latest

FROM ${DEPS_IMAGE} AS build

ARG BUILD_JOBS=8

ENV CMAKE_BUILD_PARALLEL_LEVEL=${BUILD_JOBS}

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

FROM ${NODE_EXPORTER_IMAGE} AS node-exporter

FROM ${STATIC_IMAGE}

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
