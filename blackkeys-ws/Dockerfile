FROM cgr.dev/chainguard/wolfi-base:latest AS builder

ARG PYTHON_PACKAGE_VERSION=3.13.14-r3

RUN apk add --no-cache \
    build-base \
    libmemcached-dev \
    py3.13-pip \
    "python-3.13=${PYTHON_PACKAGE_VERSION}" \
    "python-3.13-dev=${PYTHON_PACKAGE_VERSION}" \
    zlib-dev

RUN python3.13 -m venv /opt/pdm \
    && /opt/pdm/bin/pip install --no-cache-dir pdm==2.29.0

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
        "python-3.13=${PYTHON_PACKAGE_VERSION}"

FROM cgr.dev/chainguard/static:latest

ENV PATH="/app/.venv/bin:/usr/bin" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /runtime/ /
COPY --from=builder --chown=65532:65532 /app/.venv/ /app/.venv/
COPY --chown=65532:65532 blackkeys/ /app/blackkeys/
COPY --chown=65532:65532 ws.py /app/ws.py

USER 65532:65532

EXPOSE 8000

ENTRYPOINT ["/app/.venv/bin/python", "-m", "sanic"]
CMD ["ws:app", "--host=0.0.0.0", "--port=8000"]
