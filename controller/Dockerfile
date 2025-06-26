# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

ARG RUNTIME_OS_IMAGE=ubuntu:22.04

# -------------- Controller Builder Stage --------------
FROM scenescape-common-base AS scenescape-controller-builder

USER root
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
    && ${BUILD_ENV_DIR}/bin/pip3 install --no-cache-dir wheel

ENV PATH="${BUILD_ENV_DIR}/bin:${PATH}"

# Build robot vision package
COPY ./controller/src/robot_vision /tmp/robot_vision
RUN export OpenCV_DIR="/usr/lib/x86_64-linux-gnu/cmake/opencv4" \
    && cd /tmp/robot_vision \
    && python3 setup.py bdist_wheel \
    && cd dist \
    && ${BUILD_ENV_DIR}/bin/pip3 install --no-cache-dir ./*.whl \
    && cd \
   && rm -rf /tmp/robot_vision

# Build main controller package
COPY ./controller/src/controller /tmp/controller/controller
COPY ./controller/src/setup.py /tmp/controller/setup.py
RUN cd /tmp/controller \
    && python3 setup.py bdist_wheel \
    && ${BUILD_ENV_DIR}/bin/pip3 install --no-cache-dir ./dist/*.whl -vvv \
    && cd \
    && rm -rf /tmp/controller

# -------------- Controller Runtime Stage --------------
FROM ${RUNTIME_OS_IMAGE} AS scenescape-controller-runtime

ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com
ARG PYTHON_VERSION=3.10

ENV PYTHON_VERSION=${PYTHON_VERSION}
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape
ENV BUILD_ENV_DIR=/tmp/venv
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libopencv-contrib4.5d \
        libpython3.10 \
        netbase \
        python3-pip \
    && rm -rf /usr/lib/x86_64-linux-gnu/libLLVM-15.so.1 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN : \
    && useradd -r -m -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER \
    && eval WSHOME=~$WSUSER \
    && chmod a+rX "${WSHOME}"

# TODO: uncomment when issue with accessing the secrets is resolved
# USER $WSUSER

# copy installed scenescape packages from the previous stages
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base /usr/local/lib/python${PYTHON_VERSION}/dist-packages/fast_geometry /usr/local/lib/python${PYTHON_VERSION}/dist-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base /usr/local/lib/python${PYTHON_VERSION}/dist-packages/scene_common /usr/local/lib/python${PYTHON_VERSION}/dist-packages/scene_common
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder ${BUILD_ENV_DIR}/lib/python${PYTHON_VERSION}/site-packages/controller /usr/local/lib/python${PYTHON_VERSION}/dist-packages/controller
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder ${BUILD_ENV_DIR}/lib/python${PYTHON_VERSION}/site-packages/robot_vision /usr/local/lib/python${PYTHON_VERSION}/dist-packages/robot_vision

# install only required runtime dependencies
COPY controller/requirements-runtime.txt /tmp
RUN : \
    && pip3 install --upgrade --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm -rf /tmp/requirements-runtime.txt

COPY --chown=$WSUSER:$WSUSER ./controller/src/schema/metadata.schema.json $SCENESCAPE_HOME/schema/metadata.schema.json
COPY --chown=$WSUSER:$WSUSER ./controller/config/tracker-config.json $SCENESCAPE_HOME/tracker-config.json
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker
COPY --chown=$WSUSER:$WSUSER ./controller/src/controller-cmd $SCENESCAPE_HOME/controller-cmd
COPY --chown=$WSUSER:$WSUSER ./controller/src/controller-init /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/controller-init"]
