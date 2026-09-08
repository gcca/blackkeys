# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=cgr.dev/chainguard/wolfi-base:latest
ARG PDM_VERSION=2.29.0

FROM ${BASE_IMAGE} AS deps

ARG PDM_VERSION

RUN apk add --no-cache \
    build-base \
    libmemcached-dev \
    py3.13-pip \
    python-3.13 \
    python-3.13-dev \
    zlib-dev

RUN python3.13 -m venv /opt/pdm \
    && /opt/pdm/bin/pip install --no-cache-dir "pdm==${PDM_VERSION}"

ENV PATH="/opt/pdm/bin:${PATH}" \
    PDM_CHECK_UPDATE=false \
    PDM_IGNORE_ACTIVE_VENV=1

WORKDIR /app

COPY pyproject.toml pdm.lock ./

RUN pdm config venv.in_project true \
    && pdm install --check --prod --no-editable --no-self

RUN mkdir /runtime \
    && apk --root /runtime \
        --initdb \
        --keys-dir /etc/apk/keys \
        --repositories-file /etc/apk/repositories \
        add --no-cache \
        libmemcached \
        libstdc++ \
        python-3.13 \
    && mkdir -p /runtime/app /runtime/data \
    && chown 65532:65532 /runtime/app /runtime/data
