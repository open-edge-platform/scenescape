# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM scenescape-common-base AS scenescape-cluster-analytics-builder

# -------------- Cluster Analytics Runtime Stage --------------
FROM python:3.11-slim-bookworm AS scenescape-cluster-analytics-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Intel® SceneScape's Scene Cluster Analytics Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/README.md"

ARG USER_ID=1001
ARG GROUP_ID=1001
ARG CERTDOMAIN=scenescape.intel.com
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Update and upgrade base OS packages
RUN apt update && apt upgrade -y

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    # Create non-root user
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER

# Upgrade pip, wheel and setuptools to latest versions
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --upgrade setuptools wheel

COPY cluster_analytics/requirements-runtime.txt cluster_analytics/tools/webui/requirements-webui.txt /tmp/
RUN pip install --no-cache-dir \
        -r /tmp/requirements-runtime.txt \
        -r /tmp/requirements-webui.txt \
    && rm -rf /tmp/*.txt

# Copy compiled packages from builder (use system site-packages directly)
COPY --chown=$WSUSER:$WSUSER --from=scenescape-cluster-analytics-builder \
    /usr/local/lib/python3.11/site-packages/scene_common \
    /usr/local/lib/python3.11/site-packages/scene_common

COPY --chown=$WSUSER:$WSUSER --from=scenescape-cluster-analytics-builder \
    /usr/local/lib/python3.11/site-packages/fast_geometry \
    /usr/local/lib/python3.11/site-packages/fast_geometry

# Copy tools
COPY --chown=$USER_ID:$GROUP_ID --from=scenescape-cluster-analytics-builder \
    /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker

# Copy application code, config, and tools
COPY --chown=$USER_ID:$GROUP_ID ./cluster_analytics/src /app
COPY --chown=$USER_ID:$GROUP_ID ./cluster_analytics/config /app/config
COPY --chown=$USER_ID:$GROUP_ID ./cluster_analytics/tools /app/tools

USER $USER_ID:$GROUP_ID
HEALTHCHECK CMD true

ENTRYPOINT ["python3", "/app/cluster_analytics.py"]

# ---------- Cluster Analytics Test Stage ------------------
FROM scenescape-cluster-analytics-runtime AS scenescape-cluster-analytics-test
