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
FROM scenescape-common-base-24-04 AS scenescape-cluster-analytics-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Intel® SceneScape's Scene Cluster Analytics Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/README.md"

ARG USER_ID=1001
ARG GROUP_ID=1001
ARG CERTDOMAIN=scenescape.intel.com
ARG PYTHON_VERSION=3.12

ENV PYTHON_VERSION=${PYTHON_VERSION}
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape
ENV BUILD_ENV_DIR=/tmp/venv
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        gosu \
        libgl1 \
        libopencv-contrib406t64 \
        libpython3.12 \
        netbase \
    && rm -rf /usr/lib/x86_64-linux-gnu/libLLVM-15.so.1 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN : \
    # delete ubuntu user if exists
    && userdel -f -r ubuntu || true \
    # create scenescape user
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER \
    && eval WSHOME=~$WSUSER \
    && chmod a+rX "${WSHOME}"

# Install only required runtime dependencies
COPY cluster_analytics/requirements-runtime.txt /tmp
RUN : \
    && pip3 install --break-system-packages --upgrade --no-cache-dir --ignore-installed -r /tmp/requirements-runtime.txt \
    && rm -rf /tmp/requirements-runtime.txt

# Install WebUI dependencies with hash verification
COPY cluster_analytics/tools/webui/requirements-webui.txt /tmp
RUN : \
    && pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements-webui.txt \
    && rm -rf /tmp/requirements-webui.txt

COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /usr/local/lib/python${PYTHON_VERSION}/dist-packages/fast_geometry /usr/local/lib/python${PYTHON_VERSION}/dist-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /usr/local/lib/python${PYTHON_VERSION}/dist-packages/scene_common /usr/local/lib/python${PYTHON_VERSION}/dist-packages/scene_common
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker

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
