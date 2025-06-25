# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

FROM ubuntu:22.04

RUN apt-get update && apt-get install -y build-essential pkg-config python3 python3-setuptools python3-wheel cmake build-essential googletest python3-dev pybind11-dev libpython3-dev libopencv-dev libeigen3-dev

wget -O opencv.zip https://github.com/opencv/opencv/archive/master.zip
unzip opencv.zip
# Create build directory
mkdir -p build && cd build
# Configure
cmake  ../opencv-master
# Build
cmake --build .
