# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config python3 python3-setuptools python3-wheel cmake googletest python3-dev pybind11-dev libpython3-dev libopencv-dev libeigen3-dev unzip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN wget -O opencv.zip https://github.com/opencv/opencv/archive/master.zip && unzip opencv.zip && \
# Create build directory
mkdir -p build

WORKDIR /build
# Configure and build
RUN cmake  ../opencv-master && cmake --build .
