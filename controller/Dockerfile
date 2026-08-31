# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=ubuntu:26.04@sha256:2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b

# -------------- Controller Builder Stage --------------
FROM intel/scenescape-common-base AS scenescape-controller-builder

USER root
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libopencv-dev \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Build robot vision package
# numpy is already pinned in scenescape-common-base (via scene_common/requirements.txt)
# ensuring ABI compatibility for all C extensions compiled here and in the base image.
# Install with --no-deps: --ignore-installed would otherwise rebuild apt scipy via meson.
COPY ./controller/src/robot_vision /tmp/robot_vision
RUN pip3 install --break-system-packages --ignore-installed --no-cache-dir scikit-build-core networkx \
    && export OpenCV_DIR="/usr/lib/x86_64-linux-gnu/cmake/opencv4" \
    && cd /tmp/robot_vision \
    && pip3 install --break-system-packages --ignore-installed --no-cache-dir --no-build-isolation --no-deps . \
    && rm -rf /tmp/robot_vision

# Build main controller package
COPY ./controller/src/controller /tmp/controller/controller
COPY ./controller/src/setup.py /tmp/controller/setup.py
RUN cd /tmp/controller \
    && python3 setup.py bdist_wheel \
    && pip3 install --break-system-packages --ignore-installed --no-cache-dir ./dist/*.whl -vvv \
    && cd \
    && rm -rf /tmp/controller

# -------------- Controller Runtime Stage --------------
FROM ${RUNTIME_OS_IMAGE} AS scenescape-controller-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Scenescape's Scene Controller Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/docs/user-guide/microservices/controller/controller.md"

ARG USER_ID=1001
ARG GROUP_ID=1001
ARG CERTDOMAIN=scenescape.intel.com
# Ubuntu 26.04 ships Python 3.14; pip --break-system-packages installs to dist-packages.
ARG PY_LIB_DIR=python3.14
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/Scenescape
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

# Update and upgrade base OS packages
RUN apt update && apt upgrade -y

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        gosu \
        libgl1 \
        libopencv-contrib410 \
        libopencv-stitching410 \
        libpython3.14 \
        netbase \
        python3 \
        python3-open3d \
        python3-pip \
        python-is-python3 \
        sudo \
    && rm -rf /usr/lib/x86_64-linux-gnu/libLLVM-15.so.1 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN : \
    # delete ubuntu user/group if exists (UID/GID 1000 on Ubuntu 26.04)
    && userdel -f -r ubuntu || true \
    && groupdel ubuntu || true \
    # create scenescape user
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER \
    && eval WSHOME=~$WSUSER \
    && chmod a+rX "${WSHOME}"

# install only required runtime dependencies
COPY controller/requirements-runtime.txt /tmp
RUN : \
    && pip3 install --break-system-packages --ignore-installed --upgrade --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm -rf /tmp/requirements-runtime.txt

# WORKAROUND: Force upgrade protobuf to a secure version, even though vdms pins an older version.
# This may break vdms if it is not compatible with newer protobuf, but is required to fix CVE-2025-4565.
# Remove this when vdms supports a secure protobuf version.
RUN pip3 install --break-system-packages --ignore-installed --upgrade --no-cache-dir 'protobuf>=4.25.8'

# copy installed scenescape packages from the previous stages
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder /usr/local/lib/${PY_LIB_DIR}/dist-packages/fast_geometry /usr/local/lib/${PY_LIB_DIR}/dist-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder /usr/local/lib/${PY_LIB_DIR}/dist-packages/scene_common /usr/local/lib/${PY_LIB_DIR}/dist-packages/scene_common
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder /usr/local/lib/${PY_LIB_DIR}/dist-packages/controller /usr/local/lib/${PY_LIB_DIR}/dist-packages/controller
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder /usr/local/lib/${PY_LIB_DIR}/dist-packages/robot_vision /usr/local/lib/${PY_LIB_DIR}/dist-packages/robot_vision

COPY --chown=$WSUSER:$WSUSER ./controller/src/schema/metadata.schema.json $SCENESCAPE_HOME/schema/metadata.schema.json
COPY --chown=$WSUSER:$WSUSER ./tracker/schema/scene-data.schema.json $SCENESCAPE_HOME/tracker/schema/scene-data.schema.json
COPY --chown=$WSUSER:$WSUSER ./controller/config/tracker-config.json $SCENESCAPE_HOME/tracker-config.json
COPY --chown=$WSUSER:$WSUSER ./controller/config/reid-config.json $SCENESCAPE_HOME/reid-config.json
COPY --chown=$WSUSER:$WSUSER ./controller/config/pose-adjustment-route.json $SCENESCAPE_HOME/pose-adjustment-route.json
COPY --chown=$WSUSER:$WSUSER --from=scenescape-controller-builder /tmp/tools/waitforbroker $SCENESCAPE_HOME/tools/waitforbroker
COPY --chown=$WSUSER:$WSUSER ./controller/src/controller-cmd $SCENESCAPE_HOME/controller-cmd

USER $USER_ID:$GROUP_ID
HEALTHCHECK CMD true
ENTRYPOINT ["/home/scenescape/Scenescape/controller-cmd"]

# ---------- Controller Test Stage ------------------
# This stage is meant to be used for test execution (not for final runtime)
FROM scenescape-controller-runtime AS scenescape-controller-test
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

# Install Python test dependencies as root
USER root
RUN pip3 install --break-system-packages --ignore-installed --upgrade --no-cache-dir coverage==7.9.2 pytest==8.4.1 psutil plyfile==1.0.3


RUN : \
    ; eval WSHOME=~$WSUSER \
    ;

# Execute tests as the scenescape user
USER $USER_ID:$GROUP_ID

# ENTRYPOINT runs all arguments as a single, properly quoted command.
# This pattern allows the container to execute any command passed at runtime (e.g., via docker run or a wrapper script),
# preserving spaces and special characters. The -- makes all following arguments available as $@, and exec "$@" runs them as a command.
ENTRYPOINT ["/bin/bash", "-c", "exec \"$@\"", "--"]
