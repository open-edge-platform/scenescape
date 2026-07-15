# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# NOTE: No robot_vision build stage — the analytics service does not use the
# C++ tracking extension.  AnalyticsScene and AnalyticsService are designed
# to be importable without robot_vision present.

ARG RUNTIME_OS_IMAGE=python:3.11-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d

# -------------- Analytics Builder Stage --------------
FROM scenescape-common-base AS scenescape-analytics-builder

USER root
ENV DEBIAN_FRONTEND=noninteractive

# Build controller package (analytics sub-package lives here)
COPY ./controller/src/controller /tmp/controller/controller
COPY ./controller/src/setup.py /tmp/controller/setup.py
RUN cd /tmp/controller \
    && python3 setup.py bdist_wheel \
    && pip3 install --no-cache-dir ./dist/*.whl -vvv \
    && cd \
    && rm -rf /tmp/controller

# -------------- Analytics Runtime Stage --------------
FROM ${RUNTIME_OS_IMAGE} AS scenescape-analytics-runtime

LABEL org.opencontainers.image.description="Scenescape Analytics Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"

ARG USER_ID=1001
ARG GROUP_ID=1001
ARG CERTDOMAIN=scenescape.intel.com
ARG PYTHON_VERSION=3.11

ENV PYTHON_VERSION=${PYTHON_VERSION}
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/Scenescape
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

RUN apt update && apt upgrade -y \
    && apt-get install -y --no-install-recommends \
        gosu \
        libgl1 \
        libpython3.11 \
        netbase \
        python3-pip \
        sudo \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN : \
    && userdel -f -r ubuntu || true \
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER \
    && eval WSHOME=~$WSUSER \
    && chmod a+rX "${WSHOME}"

RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir --upgrade setuptools wheel

COPY analytics/requirements-runtime.txt /tmp
RUN pip3 install --break-system-packages --upgrade --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm -rf /tmp/requirements-runtime.txt

# Copy installed packages from builder
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /usr/local/lib/python${PYTHON_VERSION}/site-packages/fast_geometry /usr/local/lib/python${PYTHON_VERSION}/site-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /usr/local/lib/python${PYTHON_VERSION}/site-packages/scene_common /usr/local/lib/python${PYTHON_VERSION}/site-packages/scene_common
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /usr/local/lib/python${PYTHON_VERSION}/site-packages/controller /usr/local/lib/python${PYTHON_VERSION}/site-packages/controller

# Schema file consumed by the analytics service at startup
COPY --chown=$WSUSER:$WSUSER ./controller/src/schema/metadata.schema.json $SCENESCAPE_HOME/schema/metadata.schema.json
COPY --chown=$WSUSER:$WSUSER ./tracker/schema/scene-data.schema.json $SCENESCAPE_HOME/tracker/schema/scene-data.schema.json
COPY --chown=$WSUSER:$WSUSER --from=scenescape-analytics-builder /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker
COPY --chown=$WSUSER:$WSUSER ./analytics/src/analytics-cmd $SCENESCAPE_HOME/analytics-cmd

USER $USER_ID:$GROUP_ID
HEALTHCHECK CMD true
ENTRYPOINT ["/home/scenescape/Scenescape/analytics-cmd"]
