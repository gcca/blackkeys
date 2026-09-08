ARG C3_PLATFORM=linux/amd64

FROM --platform=${C3_PLATFORM} cgr.dev/chainguard/wolfi-base:latest AS build

ARG C3_VERSION=0.8.2
ARG C3_SHA256=dda062e791359d01549c5d1aefbac5ac88dcd9c6f84e0b2d3309e92f8f6600aa
ARG LIBMEMCACHED_COMMIT=92d18858b417309f6bdee6bce464a4f3d6a375fd

RUN apk add --no-cache \
        binutils \
        bison \
        build-base \
        clang \
        cmake \
        curl \
        flatbuffers \
        flatbuffers-dev \
        flex \
        git \
        libstdc++-dev \
        rabbitmq-c-dev

RUN curl -fsSL "https://github.com/c3lang/c3c/releases/download/v${C3_VERSION}/c3-linux-static.tar.gz" -o /tmp/c3.tar.gz \
    && echo "${C3_SHA256}  /tmp/c3.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/c3.tar.gz -C /opt \
    && rm /tmp/c3.tar.gz

ENV PATH="/opt/c3:${PATH}"

RUN git clone --branch 1.1.4 --depth 1 https://github.com/awesomized/libmemcached.git /tmp/libmemcached \
    && test "$(git -C /tmp/libmemcached rev-parse HEAD)" = "${LIBMEMCACHED_COMMIT}" \
    && cmake -S /tmp/libmemcached -B /tmp/libmemcached/build \
        -DBUILD_DOCS=OFF \
        -DBUILD_SHARED_LIBS=OFF \
        -DBUILD_TESTING=OFF \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_LIBDIR=lib \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DENABLE_MEMASLAP=OFF \
        -DENABLE_SASL=OFF \
    && cmake --build /tmp/libmemcached/build --parallel \
    && cmake --install /tmp/libmemcached/build \
    && rm -rf /tmp/libmemcached

WORKDIR /src
COPY . .

RUN mkdir -p build/generated \
    && flatc --cpp -o build/generated schemas/user_auth.fbs schemas/user_signup.fbs schemas/hydration_message.fbs \
    && clang++ -std=c++17 -Ibuild/generated -I/usr/include -c src/interop/fbufs.cpp -o build/fbufs.o

RUN cp project.linux.json project.json \
    && c3c --trust=full build blackkeys-hydrant -z -static \
    && ! readelf -lW build/blackkeys-hydrant | grep -q INTERP \
    && ! readelf -dW build/blackkeys-hydrant | grep -q NEEDED

FROM --platform=${C3_PLATFORM} cgr.dev/chainguard/static:latest

COPY --from=build --chown=nonroot:nonroot /src/build/blackkeys-hydrant /usr/local/bin/blackkeys-hydrant

ENTRYPOINT ["/usr/local/bin/blackkeys-hydrant"]
