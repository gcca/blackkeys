# syntax=docker/dockerfile:1.7

ARG DEPS_IMAGE=ghcr.io/gcca/blackkeys:ws-deps
ARG NODE_EXPORTER_IMAGE=quay.io/prometheus/node-exporter:v1.11.0
ARG STATIC_IMAGE=cgr.dev/chainguard/static:latest

FROM ${DEPS_IMAGE} AS builder

WORKDIR /app

COPY pyproject.toml pdm.lock ./

RUN pdm lock --check \
    && pdm sync --prod --no-editable --no-self --clean

FROM ${NODE_EXPORTER_IMAGE} AS node-exporter

FROM ${STATIC_IMAGE}

ENV PATH="/app/.venv/bin:/usr/bin" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /runtime/ /
COPY --from=node-exporter --chown=65532:65532 /bin/node_exporter /usr/bin/node_exporter
COPY --from=builder --chown=65532:65532 /app/.venv/ /app/.venv/
COPY --chown=65532:65532 blackkeys/ /app/blackkeys/
COPY --chown=65532:65532 ws.py /app/ws.py

USER 65532:65532

EXPOSE 8000 9100

ENTRYPOINT ["/app/.venv/bin/python", "-m", "blackkeys.commands.boot"]
CMD ["ws:app", "--host=0.0.0.0", "--port=8000"]
