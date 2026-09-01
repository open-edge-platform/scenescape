# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# -------------- Common Base Stage --------------
FROM python:3.14-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS scenescape-common-base

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
