# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

FROM intel/scenescape-common-base AS scenescape-reid-builder

FROM ${RUNTIME_OS_IMAGE} AS scenescape-reid-runtime

LABEL org.opencontainers.image.description="Scenescape Re-ID Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"

ARG USER_ID=1001
ARG GROUP_ID=1001
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/Scenescape
ENV PYTHONDONTWRITEBYTECODE=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER

COPY reid_service/requirements-runtime.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm -f /tmp/requirements-runtime.txt

COPY --from=scenescape-reid-builder \
    /usr/local/lib/python3.11/site-packages/scene_common \
    /usr/local/lib/python3.11/site-packages/scene_common
COPY --chown=${USER_ID}:${GROUP_ID} reid_service/src /app

USER ${USER_ID}:${GROUP_ID}
WORKDIR /app
HEALTHCHECK CMD python3 -c "import grpc; print('ready')"
ENTRYPOINT ["python3", "-m", "reid_service.server"]
