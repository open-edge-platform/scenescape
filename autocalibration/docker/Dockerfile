# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# Copyright (C) 2024-2025 Intel Corporation
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

COPY requirements-camcalib.txt /tmp
# SceneScape requirements
RUN : \
    ; apt-get update \
    ; apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        bindfs \
        curl \
        g++ \
        libboost-python-dev \
        libegl1 \
        libeigen3-dev \
        libgl1 \
        libglib2.0 \
        libgomp1 \
        libgtest-dev \
        make \
        mesa-utils \
        pybind11-dev \
        python-is-python3 \
        python3-dev \
        python3-pip \
        python3-scipy \
        sudo \
    ; apt-get purge -y python3-numpy \
    ; rm -rf /var/lib/apt/lists/* \
    ; pip3 install --upgrade --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements-camcalib.txt \
    ; rm -rf /tmp/requirements-camcalib.txt \
    ;

ENV WSUSER=scenescape

RUN : \
    ; useradd -r -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;

COPY install-apriltag.sh /tmp/
RUN : \
    ; /tmp/install-apriltag.sh \
    ; rm /tmp/install-apriltag.sh \
    ;

# Install Markerless Camera Calibration Package
ADD reloc.tar /tmp/
RUN set -e \
    ; cd /tmp/reloc \
    ; python3 setup.py bdist_wheel \
    ; cd dist \
    ; pip3 install --no-cache-dir ./*.whl \
    ; cd \
    ; rm -rf /tmp/reloc \
    ;

COPY install-netvlad-weights.sh /tmp/
RUN : \
    ; /tmp/install-netvlad-weights.sh \
    ; rm /tmp/install-netvlad-weights.sh \
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

RUN : \
    ; apt-get purge -y --auto-remove make g++ \
    ; apt-get clean \
    ;

ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape
# Be sure to update this line if the user or home directory changes
ADD camcalibration.tar $SCENESCAPE_HOME/

COPY camcalibration-init /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/camcalibration-init"]
