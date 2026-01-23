# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# -------------- Common Base Stage --------------
FROM ubuntu:24.04@sha256:353675e2a41babd526e2b837d7ec780c2a05bca0164f7ea5dbbd433d21d166fc AS scenescape-common-base-24-04

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install common build dependencies
RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        cmake \
        curl \
        g++ \
        git \
        libeigen3-dev \
        libgtest-dev \
        make \
        # Needed by fast_geometry
        pkg-config \
        pybind11-dev \
        python3-dev \
        python3-pip \
        python3-scipy \
        python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# Install common dependencies
COPY ./scene_common/src /tmp/scene_common
COPY cluster_analytics/requirements-build.txt /tmp/
RUN : \
    && cd /tmp/scene_common \
    && pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements-build.txt \
    && pip3 install --break-system-packages --no-cache-dir . \
    && make -C fast_geometry -j $(nproc) all install \
    && cd .. \
    && rm -rf scene_common \
    && rm -f /tmp/requirements-build.txt

COPY ./tools/waitforbroker /tmp/tools/waitforbroker

# -------------- Cluster Analytics Runtime Stage --------------
FROM python:3.12-slim AS scenescape-cluster-analytics-runtime

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
ENV BUILD_ENV_DIR=/opt/venv

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install only minimal runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create a venv (already optimized in slim images)
RUN python3 -m venv $BUILD_ENV_DIR
ENV PATH="$BUILD_ENV_DIR/bin:$PATH"

# Install core Python dependencies
RUN pip install --no-cache-dir --upgrade pip numpy opencv-python-headless==4.6.0.66

# Copy compiled scene_common + fast_geometry from builder
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /usr/local/lib/python3.12/dist-packages/scene_common \
    $BUILD_ENV_DIR/lib/python3.12/site-packages/scene_common

COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /usr/local/lib/python3.12/dist-packages/fast_geometry \
    $BUILD_ENV_DIR/lib/python3.12/site-packages/fast_geometry

# Add non-root user
RUN groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER

# Install app runtime Python deps
COPY cluster_analytics/requirements-runtime.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm -rf /tmp/requirements-runtime.txt

# Install WebUI dependencies
COPY cluster_analytics/tools/webui/requirements-webui.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-webui.txt \
    && rm -rf /tmp/requirements-webui.txt

# Copy tools
COPY --chown=$USER_ID:$GROUP_ID --from=scenescape-common-base-24-04 /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker

USER $USER_ID:$GROUP_ID
HEALTHCHECK CMD true

# Copy source code
COPY ./cluster_analytics/src /app
# Copy configuration
COPY ./cluster_analytics/config /app/config
# Copy WebUI tool
COPY ./cluster_analytics/tools /app/tools

# Default command to run Python code from src folder
ENTRYPOINT ["python3", "/app/cluster_analytics.py"]

# ---------- Cluster Analytics Test Stage ------------------
# This stage is meant to be used for test execution (not for final runtime)
FROM scenescape-common-base-24-04 AS scenescape-cluster-analytics-test
