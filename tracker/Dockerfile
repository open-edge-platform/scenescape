# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# --- Build stage ---
FROM debian:13-slim@sha256:905f0e07e40013bfedf13f38f00e1897b40b51d7ca7cedc01f2d2b7ec8a814eb AS builder

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
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy only the sources needed for the build
COPY tracker/CMakeLists.txt tracker/
COPY tracker/src tracker/src
COPY controller/src/robot_vision controller/src/robot_vision

# Configure and build (Release)
RUN rm -rf tracker/build \
    && cmake -S tracker -B tracker/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build tracker/build -j

# Collect all runtime library dependencies for the tracker binary
RUN mkdir -p /scenescape/runtime-libs
WORKDIR /scenescape/runtime-libs
RUN ldd /scenescape/tracker/build/tracker \
    | awk '{print $3}' \
    | grep '^/' \
    | xargs -I '{}' cp -v '{}' .
WORKDIR /scenescape

# --- Runtime stage ---
FROM gcr.io/distroless/cc-debian13@sha256:d93602c2e8facf19435442a3fd19306e77505ca722aad08e7de659f6df43e147 AS runtime

USER 10001
WORKDIR /scenescape

COPY --from=builder /scenescape/tracker/build/tracker ./tracker
COPY --from=builder /scenescape/runtime-libs/ ./lib/

ENV LD_LIBRARY_PATH=/scenescape/lib

# TODO: HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD ["/scenescape/tracker", "--healthcheck"]

CMD ["/scenescape/tracker"]
