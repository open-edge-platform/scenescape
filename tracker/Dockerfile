# SPDX-FileCopyrightText: 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=gcr.io/distroless/cc-debian13@sha256:d7ac2f9af248f31fe6270002755722afdf6875e0e49cd52b9150208e6a23875c

# --- Build stage ---
FROM debian:13-slim@sha256:26f98ccd92fd0a44d6928ce8ff8f4921b4d2f535bfa07555ee5d18f61429cf0c AS builder

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

# Configure and build
ARG GIT_COMMIT=unknown
RUN cmake -S tracker -B build -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE=/scenescape/build/conan_toolchain.cmake \
        -DCMAKE_BUILD_TYPE=${BUILD_TYPE} \
        -DGIT_COMMIT=${GIT_COMMIT} \
        -DBUILD_TESTS=OFF

RUN cmake --build build -j

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
FROM ${RUNTIME_OS_IMAGE} AS runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Intel® SceneScape Tracker Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/tracker/README.md"

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
FROM debian:13-slim@sha256:26f98ccd92fd0a44d6928ce8ff8f4921b4d2f535bfa07555ee5d18f61429cf0c AS debug

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
