# syntax=docker/dockerfile:1.9
ARG UV_VERSION=0.6
ARG PYTHON_VERSION=3.12
ARG PYTHON_BASE=${PYTHON_VERSION}-slim

# uv stage
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# build stage
FROM python:$PYTHON_BASE AS builder
SHELL ["bash", "-e", "-x", "-o", "pipefail", "-c"]

RUN <<EOT
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    build-essential \
    ca-certificates \
    cmake \
    libboost1.81-all-dev \
    libhdf5-dev \
    libopenmpi-dev \
    zlib1g-dev \
    git
EOT

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python${PYTHON_VERSION}

# for bigrandomgraphs
ENV CMAKE_POLICY_VERSION_MINIMUM=3.5

WORKDIR /code
ARG ENVIRONMENT
ARG TARGETPLATFORM

RUN \
    --mount=type=cache,target=/root/.cache/uv,id=uv-cache-${TARGETPLATFORM} \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --locked --no-install-project

RUN \
    --mount=type=cache,target=/root/.cache/uv,id=uv-cache-${TARGETPLATFORM} \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    --mount=type=bind,source=obi_one,target=obi_one \
    uv sync --locked --no-editable --no-cache

# run stage
FROM python:$PYTHON_BASE
SHELL ["bash", "-e", "-x", "-o", "pipefail", "-c"]

RUN <<EOT
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    libhdf5-103-1
EOT

RUN <<EOT
groupadd -r app
useradd -r -d /code -g app -N app
EOT

USER app
WORKDIR /code
ENV PATH="/code/.venv/bin:$PATH"
ENV PYTHONPATH="/code:$PYTHONPATH"
COPY --chown=app:app --from=builder /code/.venv/ .venv/
COPY --chown=app:app docker-cmd.sh pyproject.toml ./
COPY --chown=app:app app/ app/

ARG ENVIRONMENT
ARG APP_NAME
ARG APP_VERSION
ARG COMMIT_SHA
ENV ENVIRONMENT=${ENVIRONMENT}
ENV APP_NAME=${APP_NAME}
ENV APP_VERSION=${APP_VERSION}
ENV COMMIT_SHA=${COMMIT_SHA}
ENV OUTPUT_DIR=/tmp

RUN <<EOT
python -V
python -m site
EOT

STOPSIGNAL SIGINT
CMD ["./docker-cmd.sh"]