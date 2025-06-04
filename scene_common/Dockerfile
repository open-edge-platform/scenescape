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

# install common build dependencies
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
        python3-pip \
        # needed by fast_geometry
        python3-scipy \
        python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# install common dependencies
COPY ./scene_common/src /tmp/scene_common
RUN : \
    && cd /tmp/scene_common \
    && pip3 install --no-cache-dir pybind11 \
    && pip3 install --no-cache-dir . \
    && make -C fast_geometry -j $(nproc) all install \
    && cd .. \
    && rm -rf scene_common

COPY ./utils/waitforbroker /tmp/utils/waitforbroker
