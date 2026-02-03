# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# --- Build stage ---
FROM debian:13-slim@sha256:77ba0164de17b88dd0bf6cdc8f65569e6e5fa6cd256562998b62553134a00ef0 AS builder

WORKDIR /scenescape

ENV DEBIAN_FRONTEND=noninteractive

# Build dependencies
# hadolint ignore=DL3008
RUN apt-get update -qq \
    && apt-get install -qq -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        python3-pip \
        libopenblas-dev \
        libgomp1 \
        pkg-config \
        > /dev/null \
    && rm -rf /var/lib/apt/lists/*

# Install Conan
RUN pip3 install --no-cache-dir --break-system-packages conan==2.24

# Copy conanfile first for better layer caching
COPY tracker/conanfile.txt tracker/

# Build type: Release, Debug, or RelWithDebInfo (for profiling)
ARG BUILD_TYPE=Release

# Install Conan dependencies (layer cached locally and via GHA cache in CI)
RUN conan profile detect --force \
    && conan install tracker \
        --output-folder=build \
        --build=missing \
        -s build_type=${BUILD_TYPE} \
        -c tools.cmake.cmaketoolchain:generator=Ninja \
        -c tools.system.package_manager:mode=install

# Copy only the sources needed for the build
COPY version.txt .
COPY tracker/CMakeLists.txt tracker/
COPY tracker/src tracker/src
COPY tracker/inc tracker/inc
COPY controller/src/robot_vision controller/src/robot_vision

# Configure (cacheable - no GIT_COMMIT dependency)
RUN cmake -S tracker -B build -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE=/scenescape/build/conan_toolchain.cmake \
        -DCMAKE_BUILD_TYPE=${BUILD_TYPE} \
        -DBUILD_TESTS=OFF

# Build (GIT_COMMIT passed via env var, only recompiles version-dependent files)
ARG GIT_COMMIT=unknown
RUN GIT_COMMIT=${GIT_COMMIT} cmake --build build -j

# Collect all runtime library dependencies for the tracker binary
WORKDIR /scenescape/runtime-libs
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# hadolint ignore=SC1091
RUN mkdir -p /scenescape/runtime-libs \
    && . /scenescape/build/conanrun.sh && ldd /scenescape/build/tracker \
    | awk '{print $3}' \
    | grep '^/' \
    | xargs -I '{}' cp -v '{}' .
WORKDIR /scenescape

# --- Runtime stage ---
FROM gcr.io/distroless/cc-debian13@sha256:d7ac2f9af248f31fe6270002755722afdf6875e0e49cd52b9150208e6a23875c AS runtime

USER 10001
WORKDIR /scenescape

COPY --from=builder /scenescape/build/tracker ./tracker
COPY --from=builder /scenescape/runtime-libs/ ./lib/
COPY tracker/schema/ ./schema/
COPY tracker/config/ ./config/

ENV LD_LIBRARY_PATH=/scenescape/lib

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/scenescape/tracker", "healthcheck"]

CMD ["/scenescape/tracker", "--config", "/scenescape/config/tracker.json", "--schema", "/scenescape/schema/config.schema.json"]

# --- Debug stage (for development with gdbserver) ---
FROM debian:13-slim@sha256:77ba0164de17b88dd0bf6cdc8f65569e6e5fa6cd256562998b62553134a00ef0 AS debug

# hadolint ignore=DL3008
RUN apt-get update -qq \
    && apt-get install -qq -y --no-install-recommends \
        gdbserver \
        > /dev/null \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /scenescape

COPY --from=builder /scenescape/build/tracker ./bin/tracker
COPY --from=builder /scenescape/runtime-libs/ ./lib/
COPY tracker/schema/ ./schema/
COPY tracker/config/ ./config/

ENV LD_LIBRARY_PATH=/scenescape/lib
EXPOSE 2345

CMD ["gdbserver", "0.0.0.0:2345", "/scenescape/bin/tracker", "--config", "/scenescape/config/tracker.json", "--schema", "/scenescape/schema/config.schema.json"]
