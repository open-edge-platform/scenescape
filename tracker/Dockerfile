# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Simple demo image for tracker_hello + RobotVision
FROM debian:stable-slim

WORKDIR /scenescape

ENV DEBIAN_FRONTEND=noninteractive

# Build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        libopencv-dev \
        libeigen3-dev \
        libopenblas-dev \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy minimal sources needed for tracker_hello build
COPY . /scenescape

# Configure and build (Release)
RUN rm -rf tracker/build \
        && cmake -S tracker -B tracker/build -G Ninja \
            -DCMAKE_BUILD_TYPE=Release \
            -DOpenCV_DIR=/usr/lib/x86_64-linux-gnu/cmake/opencv4 \
            -DBUILD_TESTING=OFF \
            -DBUILD_BENCHMARKS=OFF \
        && cmake --build tracker/build -j

# Simple runtime: reuse the same image for now
WORKDIR /scenescape/tracker/build

CMD ["./tracker"]
