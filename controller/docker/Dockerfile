# -*- mode: Fundamental; indent-tabs-mode: nil -*-

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

FROM ubuntu:22.04

# We use root for runtime init. The command in ENTRYPOINT will drop to an unprivileged user.
# hadolint ignore=DL3002
USER root

SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com

ENV DEBIAN_FRONTEND=noninteractive

# SceneScape requirements #Change this to just controller requirements?
COPY requirements-controller.txt /tmp
RUN : \
    ; apt-get update \
    ; apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        cmake \
        curl \
        g++ \
        git \
        libeigen3-dev \
        libglib2.0-0 \
        libgl1-mesa-glx \
        libgtest-dev \
        libopencv-dev \
        make \
        netbase \
        patch \
        pybind11-dev \
        python-is-python3 \
        python3-opencv \
        python3-pip \
        python3-scipy \
        sudo \
    ; apt-get purge -y python3-numpy \
    ; pip3 install --upgrade --no-cache-dir \
        -r /tmp/requirements-controller.txt \
    ; rm -rf /tmp/requirements-controller.txt \
    ;

ENV WSUSER=scenescape

RUN : \
    ; useradd -r -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;

ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

# Install robot vision package
ADD robot_vision.tar /tmp/
RUN : \
    ; export OpenCV_DIR="/usr/lib/x86_64-linux-gnu/cmake/opencv4" \
    ; cd /tmp/robot_vision \
    ; python3 setup.py bdist_wheel \
    ; cd dist \
    ; pip3 install --no-cache-dir ./*.whl \
    ; cd \
    ; rm -rf /tmp/robot_vision \
    ;

# Install scene common
ADD scene_common.tar tmp/
RUN : \
    ; cd tmp/scene_common \
    ; pip install --no-cache-dir . \
    ; make -C fast_geometry -j $(nproc) all install \
    ; cd .. \
    ; rm -rf scene_common \
    ;

ADD controller.tar $SCENESCAPE_HOME/
RUN : \
    ; eval WSHOME=~$WSUSER \
    ; chown -R "$WSUSER" "$SCENESCAPE_HOME" \
    ; pip3 install --no-cache-dir "$SCENESCAPE_HOME/" \
    ;

RUN : \
    ; apt-get purge -y --auto-remove make cmake git \
    ; apt-get clean \
    ; rm -rf /var/lib/apt/lists/* \
    ;

COPY controller-init /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/controller-init"]
