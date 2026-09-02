# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# NOTE: No robot_vision build stage — the analytics service does not use the
# C++ tracking extension.  AnalyticsScene and AnalyticsService are designed
# to be importable without robot_vision present.

ARG RUNTIME_OS_IMAGE=python:3.14-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f

# -------------- Analytics Builder Stage --------------
FROM intel/scenescape-common-base AS scenescape-analytics-builder

USER root
ENV DEBIAN_FRONTEND=noninteractive

# Build analytics package
COPY ./analytics/src/analytics /tmp/analytics/analytics
COPY ./analytics/src/setup.py /tmp/analytics/setup.py
RUN cd /tmp/analytics \
    && python3 setup.py bdist_wheel \
    && pip3 install --break-system-packages --ignore-installed --no-cache-dir ./dist/*.whl -vvv \
    && cd \
    && rm -rf /tmp/analytics

# -------------- Analytics Runtime Stage --------------
FROM ${RUNTIME_OS_IMAGE} AS scenescape-analytics-runtime

LABEL org.opencontainers.image.description="Scenescape Analytics Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"

ARG USER_ID=1001
ARG GROUP_ID=1001
ARG CERTDOMAIN=scenescape.intel.com
ARG PYTHON_VERSION=3.14
ARG PY_LIB_DIR=python3.14

ENV PYTHON_VERSION=${PYTHON_VERSION}
ENV PY_LIB_DIR=${PY_LIB_DIR}
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/Scenescape
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

RUN apt update && apt upgrade -y \
    && apt-get install -y --no-install-recommends \
    gosu \
    libgl1 \
    libgomp1 \
    libatomic1 \
    libusb-1.0-0 \
    netbase \
    sudo \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN : \
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER \
    && eval WSHOME=~$WSUSER \
    && chmod a+rX "${WSHOME}"

COPY requirements-open3d-cpu.txt tools/install-open3d-cpu.sh /tmp/
COPY analytics/requirements-runtime.txt /tmp/
RUN pip3 install --break-system-packages --ignore-installed --upgrade --no-cache-dir -r /tmp/requirements-runtime.txt \
    && /tmp/install-open3d-cpu.sh /tmp/requirements-open3d-cpu.txt pip3 \
    && rm -f /tmp/requirements-runtime.txt /tmp/requirements-open3d-cpu.txt /tmp/install-open3d-cpu.sh

# Copy installed packages from builder
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /usr/local/lib/${PY_LIB_DIR}/site-packages/fast_geometry /usr/local/lib/${PY_LIB_DIR}/site-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /usr/local/lib/${PY_LIB_DIR}/site-packages/scene_common /usr/local/lib/${PY_LIB_DIR}/site-packages/scene_common
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /usr/local/lib/${PY_LIB_DIR}/site-packages/analytics /usr/local/lib/${PY_LIB_DIR}/site-packages/analytics

# Schema file consumed by the analytics service at startup
COPY --chown=$WSUSER:$WSUSER ./controller/src/schema/metadata.schema.json $SCENESCAPE_HOME/schema/metadata.schema.json
COPY --chown=$WSUSER:$WSUSER ./tracker/schema/scene-data.schema.json $SCENESCAPE_HOME/tracker/schema/scene-data.schema.json
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker
COPY --chown=$WSUSER:$WSUSER ./analytics/src/analytics-cmd $SCENESCAPE_HOME/analytics-cmd

USER $USER_ID:$GROUP_ID
HEALTHCHECK CMD true
ENTRYPOINT ["/home/scenescape/Scenescape/analytics-cmd"]

# -------------- Analytics Test Stage --------------
FROM scenescape-analytics-runtime AS scenescape-analytics-test
