
# --- Build stage ---
FROM debian:13-slim@sha256:905f0e07e40013bfedf13f38f00e1897b40b51d7ca7cedc01f2d2b7ec8a814eb AS builder

WORKDIR /scenescape

# Set environment variables for non-interactive installs
ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        python3-pip \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install specific version of Conan
RUN --mount=type=cache,id=tracker-pip-cache,target=/root/.cache/pip \
    pip3 install --break-system-packages conan==2.23.0

# Install dependencies via Conan
COPY tracker/conanfile.txt ./
RUN --mount=type=cache,id=tracker-conan-cache,target=/root/.conan2 \
    conan profile detect --force \
    && CONAN_CMAKE_GENERATOR=Ninja conan install . --output-folder=build-release --build=missing -s build_type=Release -c tools.system.package_manager:mode=install

# Create a directory with all required libraries from Conan cache
RUN --mount=type=cache,id=tracker-conan-cache,target=/root/.conan2 mkdir -p runtime-libs && \
    cd runtime-libs && \
    find ~/.conan2/p -name "*.so*" -path "*/Release/*" -type f -exec cp {} . \; && \    
    cp /usr/lib/x86_64-linux-gnu/libgomp.so.1* .  && \
    cp /lib/x86_64-linux-gnu/libm.so.6 .  && \       
    for lib in libopencv_*.so.4.12.0; do \
        mv "$lib" "${lib%.so.4.12.0}.so.412"; \
    done

# Copy source files
COPY tracker/CMakeLists.txt tracker/Makefile ./
COPY tracker/src ./src
COPY tracker/inc ./inc
COPY controller/src/robot_vision /controller/src/robot_vision

# Build the tracker service
RUN --mount=type=cache,id=tracker-conan-cache,target=/root/.conan2 make build-release

# --- Runtime stage ---
FROM gcr.io/distroless/cc-debian13@sha256:d93602c2e8facf19435442a3fd19306e77505ca722aad08e7de659f6df43e147 AS runtime

USER 1000:1000
WORKDIR /scenescape

# Copy executable and custom libraries
COPY --from=builder /scenescape/build-release/tracker ./tracker
COPY --from=builder /scenescape/build-release/robot_vision/libRobotVision.so ./lib/libRobotVision.so

# Copy all runtime libraries
COPY --from=builder /scenescape/runtime-libs/ ./lib/

# Set library path for runtime libraries
ENV LD_LIBRARY_PATH=/scenescape/lib

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["/scenescape/tracker", "healthcheck", "--type", "readiness"]

ENTRYPOINT ["/scenescape/tracker"]