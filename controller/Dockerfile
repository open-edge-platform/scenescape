# Copyright (C) 2021-2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

# -------------- Common Base Stage --------------
FROM ubuntu:22.04 AS scenescape-common-base

# We use root for runtime init. The command in ENTRYPOINT will drop to an unprivileged user.
# hadolint ignore=DL3002
USER root
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        g++ \
        make \
        python3-pip \
        # needed by fast_geometry
        python3-scipy \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

ENV BUILD_ENV_DIR=/tmp/venv

# create and set up Python virtual environment
RUN : \
    && mkdir ${BUILD_ENV_DIR} \
    && python3 -m venv ${BUILD_ENV_DIR} \
    && ${BUILD_ENV_DIR}/bin/pip3 install --upgrade --no-cache-dir pip \
    && ${BUILD_ENV_DIR}/bin/pip3 install --no-cache-dir wheel \
    && ${BUILD_ENV_DIR}/bin/pip install --no-cache-dir wheel

ENV PATH="${BUILD_ENV_DIR}/bin:${PATH}"

# install common dependencies
COPY ./scene_common tmp/scene_common
RUN : \
    && cd tmp/scene_common \
    && pip install --no-cache-dir pybind11 \
    && pip install --no-cache-dir . \
    && make -C fast_geometry -j $(nproc) all install \
    && cd .. \
    && rm -rf scene_common

COPY ./utils/waitforbroker /tmp/utils/waitforbroker

# -------------- Controller Builder Stage --------------
FROM ubuntu:22.04 AS scenescape-controller-builder

USER root
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# TODO: copy common dependencies from previous stages instead of install
RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        cmake \
        libeigen3-dev \
        libgtest-dev \
        libopencv-dev \
        make \
        pybind11-dev \
        python3-pip \
        python3-scipy \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Set up Python virtual environment for building
ENV BUILD_ENV_DIR=/tmp/venv
COPY --from=scenescape-common-base $BUILD_ENV_DIR $BUILD_ENV_DIR
ENV PATH="${BUILD_ENV_DIR}/bin:${PATH}"
ENV WHEEL_DIR=/tmp/wheelhouse

# Install 3rd party python dependencies
COPY controller/requirements-buildtime.txt /tmp
RUN : \
    && pip3 download -r /tmp/requirements-buildtime.txt -d ${WHEEL_DIR} \
    && pip3 install --upgrade --no-index --find-links=${WHEEL_DIR} -r /tmp/requirements-buildtime.txt \
    && rm -rf /tmp/requirements-buildtime.txt

# Build robot vision package
COPY ./controller/src/robot_vision /tmp/robot_vision
RUN export OpenCV_DIR="/usr/lib/x86_64-linux-gnu/cmake/opencv4" \
    && cd /tmp/robot_vision \
    && python3 setup.py bdist_wheel \
    && cd dist \
    && pip3 install --no-cache-dir ./*.whl \
    && cd \
    && rm -rf /tmp/robot_vision

# Build main controller package
COPY ./controller/src/controller /tmp/controller
RUN cd /tmp/controller \
    && python3 setup.py bdist_wheel \
    && cd dist \
    && pip3 install --no-cache-dir ./*.whl \
    && cd \
    && rm -rf /tmp/controller

# TODO: use slimmer image for runtime stage
# -------------- Controller Runtime Stage --------------
FROM ubuntu:22.04 AS scenescape-controller-runtime

ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com

ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape
ENV WHEEL_DIR=/tmp/wheelhouse
ENV BUILD_ENV_DIR=/tmp/venv
ENV RUNTIME_ENV_DIR=/home/$WSUSER/venv
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

# TODO: copy common dependencies from previous stages instead of install
RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libopencv-dev \
        libpython3.10 \
        netbase \
        python-is-python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN : \
    && useradd -r -m -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER \
    && eval WSHOME=~$WSUSER \
    && chmod a+rX "${WSHOME}"

# TODO: uncomment when issue with accessing the secrets is resolved
# USER $WSUSER

# setup up runtime Python virtual environment
RUN : \
    && mkdir ${RUNTIME_ENV_DIR} \
    && python3 -m venv ${RUNTIME_ENV_DIR} \
    && ${RUNTIME_ENV_DIR}/bin/pip3 install --upgrade --no-cache-dir pip \
    && ${RUNTIME_ENV_DIR}/bin/pip3 install --no-cache-dir wheel
ENV PATH="${RUNTIME_ENV_DIR}/bin:${PATH}"

# copy wheels from the builder stage
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder ${WHEEL_DIR} ${WHEEL_DIR}
# copy installed scenescape packages from the previous stages
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base /usr/local/lib/python3.10/dist-packages/fast_geometry ${RUNTIME_ENV_DIR}/lib/python3.10/site-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base ${BUILD_ENV_DIR}/lib/python3.10/site-packages/scene_common ${RUNTIME_ENV_DIR}/lib/python3.10/site-packages/scene_common
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base ${BUILD_ENV_DIR}/lib/python3.10/site-packages/scene_common*.dist-info ${RUNTIME_ENV_DIR}/lib/python3.10/site-packages/
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder ${BUILD_ENV_DIR}/lib/python3.10/site-packages/controller ${RUNTIME_ENV_DIR}/lib/python3.10/site-packages/controller
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder ${BUILD_ENV_DIR}/lib/python3.10/site-packages/controller*.dist-info ${RUNTIME_ENV_DIR}/lib/python3.10/site-packages/
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder ${BUILD_ENV_DIR}/lib/python3.10/site-packages/robot_vision ${RUNTIME_ENV_DIR}/lib/python3.10/site-packages/robot_vision
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder ${BUILD_ENV_DIR}/lib/python3.10/site-packages/robot_vision*.dist-info ${RUNTIME_ENV_DIR}/lib/python3.10/site-packages/

# install only required runtime dependencies
COPY controller/requirements-runtime.txt /tmp
RUN : \
    && pip3 install --upgrade --no-index --find-links=${WHEEL_DIR} -r /tmp/requirements-runtime.txt \
    && rm -rf /tmp/requirements-runtime.txt \
    && rm -rf ${WHEEL_DIR}

COPY --chown=$WSUSER:$WSUSER ./controller/src/schema/metadata.schema.json $SCENESCAPE_HOME/schema/metadata.schema.json
COPY --chown=$WSUSER:$WSUSER ./controller/config/tracker-config.json $SCENESCAPE_HOME/tracker-config.json
COPY --chown=$WSUSER:$WSUSER --from=scenescape-common-base /tmp/utils/waitforbroker $SCENESCAPE_HOME/utils/waitforbroker
COPY --chown=$WSUSER:$WSUSER ./controller/src/controller-cmd $SCENESCAPE_HOME/controller-cmd
COPY --chown=$WSUSER:$WSUSER ./controller/src/controller-init /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/controller-init"]
