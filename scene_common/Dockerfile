# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# -------------- Common Base Stage --------------
FROM ubuntu:26.04@sha256:2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b AS scenescape-common-base

# We use root for runtime init. The command in ENTRYPOINT will drop to an unprivileged user.
# hadolint ignore=DL3002
USER root
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Update and upgrade base OS packages
RUN apt update && apt upgrade -y

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
        python3-dev \
        python3-pip \
        # needed by fast_geometry
        python3-scipy \
        python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY ./scene_common/requirements.txt /tmp/scene_common_requirements.txt
# apt ships wheel/setuptools without pip RECORD files; ignore-installed overlays them.
RUN pip3 install --break-system-packages --ignore-installed --no-cache-dir \
        -r /tmp/scene_common_requirements.txt \
    && rm /tmp/scene_common_requirements.txt

# Install scene-common dependencies
COPY ./scene_common/src /tmp/scene_common
RUN : \
    && cd /tmp/scene_common \
    && pip3 install --break-system-packages --ignore-installed --no-cache-dir pybind11 \
    && pip3 install --break-system-packages --ignore-installed --no-cache-dir . \
    && make -C fast_geometry clean \
    && make -C fast_geometry -j $(nproc) all install \
    && cd .. \
    && rm -rf scene_common

COPY ./tools/waitforbroker /tmp/tools/waitforbroker
