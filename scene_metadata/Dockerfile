# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

FROM intel/scenescape-common-base AS scenescape-scene-metadata-builder

USER root
COPY ./scene_metadata/src/setup.py /tmp/scene_metadata/setup.py
COPY ./scene_metadata/src/scene_metadata /tmp/scene_metadata/scene_metadata
RUN pip3 install --no-cache-dir build \
    && cd /tmp/scene_metadata \
    && python3 -m build --wheel \
    && pip3 install --no-cache-dir ./dist/*.whl \
    && rm -rf /tmp/scene_metadata

FROM ${RUNTIME_OS_IMAGE} AS scenescape-scene-metadata-runtime

LABEL org.opencontainers.image.description="Scenescape Scene Metadata Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"

ARG USER_ID=1001
ARG GROUP_ID=1001
ENV WSUSER=scenescape
ENV PYTHONDONTWRITEBYTECODE=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER

COPY scene_metadata/requirements-runtime.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm -f /tmp/requirements-runtime.txt

COPY --from=scenescape-scene-metadata-builder \
    /usr/local/lib/python3.11/site-packages/scene_common \
    /usr/local/lib/python3.11/site-packages/scene_common
COPY --from=scenescape-scene-metadata-builder \
    /usr/local/lib/python3.11/site-packages/scene_metadata \
    /usr/local/lib/python3.11/site-packages/scene_metadata
COPY scene_metadata/sql /app/sql

USER ${USER_ID}:${GROUP_ID}
WORKDIR /app
HEALTHCHECK CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/v1/health')"
ENTRYPOINT ["python3", "-m", "scene_metadata.server"]
