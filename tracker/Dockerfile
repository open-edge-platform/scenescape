# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# --- Build stage ---
FROM debian:13-slim@sha256:4bcb9db66237237d03b55b969271728dd3d955eaaa254b9db8a3db94550b1885 AS builder

WORKDIR /scenescape

ENV DEBIAN_FRONTEND=noninteractive

# Build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        python3-pip \
        libopencv-dev \
        libeigen3-dev \
        libopenblas-dev \
        libgomp1 \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Conan
RUN pip3 install --break-system-packages conan

# Copy conanfile first for better layer caching
COPY tracker/conanfile.txt tracker/

# Install Conan dependencies with BuildKit cache for packages
RUN --mount=type=cache,id=conan-cache,target=/root/.conan2,sharing=locked \
    conan profile detect --force \
    && conan install tracker \
        --output-folder=build-release \
        --build=missing \
        -s build_type=Release \
        -c tools.cmake.cmaketoolchain:generator=Ninja \
        -c tools.system.package_manager:mode=install

# Copy only the sources needed for the build
COPY tracker/CMakeLists.txt tracker/
COPY tracker/src tracker/src
COPY tracker/inc tracker/inc
COPY controller/src/robot_vision controller/src/robot_vision

# Configure and build (Release)
RUN --mount=type=cache,id=conan-cache,target=/root/.conan2,sharing=locked \
    cmake -S tracker -B build-release -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE=/scenescape/build-release/conan_toolchain.cmake \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_TESTS=OFF \
    && cmake --build build-release -j

# Collect all runtime library dependencies for the tracker binary
RUN mkdir -p /scenescape/runtime-libs
WORKDIR /scenescape/runtime-libs
RUN ldd /scenescape/build-release/tracker \
    | awk '{print $3}' \
    | grep '^/' \
    | xargs -I '{}' cp -v '{}' .
WORKDIR /scenescape

# --- Runtime stage ---
FROM gcr.io/distroless/cc-debian13@sha256:43fc7a7004c4cdb27aac60b3e95c87130cf47823f72d25d42ed0f9b503f1d184 AS runtime

USER 10001
WORKDIR /scenescape

COPY --from=builder /scenescape/build-release/tracker ./tracker
COPY --from=builder /scenescape/runtime-libs/ ./lib/

ENV LD_LIBRARY_PATH=/scenescape/lib

# TODO: HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD ["/scenescape/tracker", "--healthcheck"]

CMD ["/scenescape/tracker"]
