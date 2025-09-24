# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=ubuntu:24.04@sha256:353675e2a41babd526e2b837d7ec780c2a05bca0164f7ea5dbbd433d21d166fc

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
        # needed by fast_geometry
        pkg-config \
        pybind11-dev \
        python3-dev \
        python3-pip \
        python3-scipy \
        python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# install common dependencies
COPY ./scene_common /tmp/scene_common
RUN : \
    && cd /tmp/scene_common \
    && mv src scene_common \
    && pip3 install --break-system-packages --no-cache-dir pybind11==3.0.0 \
    && pip3 install --break-system-packages --no-cache-dir . \
    && make -C scene_common/fast_geometry -j $(nproc) all install \
    && cd .. \
    && rm -rf scene_common

COPY ./tools/waitforbroker /tmp/tools/waitforbroker

# -------------- Analytics Builder Stage --------------
FROM scenescape-common-base-24-04 AS scenescape-analytics-builder

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libopencv-dev \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# create and set up Python virtual environment
ENV BUILD_ENV_DIR=/tmp/venv
RUN : \
    && mkdir ${BUILD_ENV_DIR} \
    && python3 -m venv ${BUILD_ENV_DIR} \
    && ${BUILD_ENV_DIR}/bin/pip3 install --upgrade --no-cache-dir pip \
    && ${BUILD_ENV_DIR}/bin/pip3 install --no-cache-dir wheel setuptools

ENV PATH="${BUILD_ENV_DIR}/bin:${PATH}"

# Copy requirements file (if you have one)
COPY requirements.txt* ./

# Install Python dependencies if requirements.txt exists
RUN if [ -f requirements.txt ]; then pip3 install --no-cache-dir -r requirements.txt; fi

# Copy source code
COPY ./analytics/src /tmp/analytics

# Default command to run Python code from src folder
CMD ["python", "/tmp/analytics/main.py"]

# -------------- Analytics Runtime Stage --------------
FROM ${RUNTIME_OS_IMAGE} AS scenescape-analytics-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Intel® SceneScape's Scene Analytics Service"
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
        python3-pip \
        sudo \
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


# install only required runtime dependencies
COPY analytics/requirements.txt /tmp
RUN : \
    && pip3 install --break-system-packages --upgrade --no-cache-dir -r /tmp/requirements.txt \
    && rm -rf /tmp/requirements.txt

# WORKAROUND: Force upgrade protobuf to a secure version, even though vdms pins an older version.
# This may break vdms if it is not compatible with newer protobuf, but is required to fix CVE-2025-4565.
# Remove this when vdms supports a secure protobuf version.
RUN pip3 install --break-system-packages --upgrade --no-cache-dir 'protobuf>=4.25.8'

# copy installed scenescape packages from the previous stages
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /usr/local/lib/python${PYTHON_VERSION}/dist-packages/fast_geometry /usr/local/lib/python${PYTHON_VERSION}/dist-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /usr/local/lib/python${PYTHON_VERSION}/dist-packages/scene_common /usr/local/lib/python${PYTHON_VERSION}/dist-packages/scene_common
COPY --chown=$WSUSER:$WSUSER ./controller/src/schema/metadata.schema.json $SCENESCAPE_HOME/schema/metadata.schema.json
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base-24-04 /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker
