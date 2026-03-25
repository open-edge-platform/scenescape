# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# -------------- Common Base Stage --------------
FROM python:3.11-slim-bookworm@sha256:420310dd2ff7895895f0f1f9d15cae5a95dabceb8f1d6b9a23ef33c2c1c542c3 AS scenescape-common-base

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
        # needed by fast_geometry
        python3-scipy \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and setuptools to latest versions
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel

# Pin numpy to the runtime version before building C extensions (fast_geometry)
# to ensure NumPy ABI compatibility between build and runtime stages.
COPY ./scene_common/requirements.txt /tmp/scene_common_requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/scene_common_requirements.txt \
    && rm /tmp/scene_common_requirements.txt

# install common dependencies
COPY ./scene_common/src /tmp/scene_common
RUN : \
    && cd /tmp/scene_common \
    && pip3 install --no-cache-dir pybind11 \
    && pip3 install --no-cache-dir . \
    && make -C fast_geometry -j $(nproc) all install \
    && cd .. \
    && rm -rf scene_common

COPY ./tools/waitforbroker /tmp/tools/waitforbroker
