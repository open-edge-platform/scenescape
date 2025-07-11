# Dockerfile for SceneScape Controller C++

FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    libopencv-dev \
    nlohmann-json3-dev \
    libpaho-mqtt-dev \
    libpaho-mqttpp-dev \
    libcpprest-dev \
    libeigen3-dev \
    libpcl-dev \
    libtbb-dev \
    libomp-dev \
    libgoogle-glog-dev \
    libgflags-dev \
    libatlas-base-dev \
    libsuitesparse-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY . /src
WORKDIR /src

# Build the application
RUN mkdir build && cd build && \
    cmake .. && \
    make -j$(nproc)

# Runtime stage
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libopencv-core4.5d \
    libopencv-imgproc4.5d \
    libpaho-mqtt1.3 \
    libpaho-mqttpp1.3 \
    libcpprest2.10 \
    libtbb12 \
    libgomp1 \
    libgoogle-glog0v5 \
    libgflags2.2 \
    && rm -rf /var/lib/apt/lists/*

# Copy binary and configuration
COPY --from=builder /src/build/controller /usr/local/bin/
COPY --from=builder /src/config/ /etc/scenescape/controller/

# Create non-root user
RUN useradd -r -s /bin/false scenescape

USER scenescape

ENTRYPOINT ["/usr/local/bin/controller"]
