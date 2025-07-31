# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# =========================
# STAGE 1: BUILD STAGE
# =========================
FROM scenescape-common-base AS camcalibration-builder
ENV DEBIAN_FRONTEND=noninteractive
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}

# Install system dependencies first (these change less frequently)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential wget && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (these change more frequently)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --upgrade \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    pybind11 dt-apriltags

# Create directories (this layer rarely changes)
RUN mkdir -p /output /tmp/apriltag_build /tmp/apriltag /tmp/netvlad

# Copy source code (this changes frequently)
COPY autocalibration/src/reloc /tmp/reloc

# Build wheels in parallel (this changes when source or dependencies change)
# Clone AprilTag
RUN git clone --depth=1 https://github.com/duckietown/lib-dt-apriltags.git /tmp/apriltag/apriltag-dev

# Build AprilTag
WORKDIR /tmp/apriltag/apriltag-dev
RUN git submodule update --init && \
    mkdir build

WORKDIR /tmp/apriltag/apriltag-dev/build
RUN cmake ../apriltags/ && make -j$(nproc)

WORKDIR /tmp/apriltag/apriltag-dev
RUN python3 setup.py bdist_wheel && \
    cp build/*.so /tmp/apriltag_build/ && \
    cp dist/*.whl /output/

# NetVLAD with on-demand loading (NO MODEL DOWNLOAD)
WORKDIR /tmp/netvlad
RUN mkdir -p third_party/netvlad && \
    touch third_party/__init__.py third_party/netvlad/__init__.py && \
    # Create setup.py without downloading the model
    echo "include third_party/netvlad/*" > MANIFEST.in && \
    echo -e "from setuptools import setup, find_packages\n\
setup(name='third_party', version='1.0.0', packages=find_packages(),\n\
package_data={'': []}, include_package_data=True)" > setup.py && \
    python3 setup.py bdist_wheel && \
    cp dist/*.whl /output/

# Build reloc wheel
RUN --mount=type=cache,target=/root/.cache/pip \
    cd /tmp/reloc && \
    python3 setup.py bdist_wheel && \
    cp dist/*.whl /output/

# =========================
# STAGE 2: RUNTIME STAGE
# =========================
# Runtime stage
FROM ubuntu:22.04 AS camcalibration-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Intel® SceneScape's Camera Calibration Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/autocalibration/docs/user-guide/overview.md"

# Define environment variables first
ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}
ENV DEBIAN_FRONTEND=noninteractive
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape
ENV PYTHONPATH="/usr/local/lib/python3.10/dist-packages"
# Set model directory for on-demand loading
ENV NETVLAD_MODEL_DIR="/usr/local/lib/python3.10/dist-packages/third_party/netvlad"

# Install runtime dependencies first (these change less frequently)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    bindfs sudo libgl1 libegl1 libglib2.0-0 libgomp1 python3 python3-pip wget && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Add user (this rarely changes)
RUN useradd -r -m -s /bin/bash $WSUSER && \
    usermod -a -G video,users $WSUSER && \
    chmod a+rX /home/$WSUSER

# Create model directory for on-demand downloads
RUN mkdir -p $NETVLAD_MODEL_DIR && \
    chown -R $WSUSER:$WSUSER $NETVLAD_MODEL_DIR

# Copy scene_common and fast_geometry from builder stage BEFORE installing other packages
COPY --from=camcalibration-builder /usr/local/lib/python3.10/dist-packages/fast_geometry /usr/local/lib/python3.10/dist-packages/fast_geometry
COPY --from=camcalibration-builder /usr/local/lib/python3.10/dist-packages/scene_common /usr/local/lib/python3.10/dist-packages/scene_common

# Copy AprilTag shared library
COPY --from=camcalibration-builder /tmp/apriltag_build/libapriltag.so /usr/local/lib/python3.10/site-packages/dt_apriltags/
RUN mkdir -p /usr/local/lib/python3.10/dist-packages/dt_apriltags/ && \
    cp /usr/local/lib/python3.10/site-packages/dt_apriltags/libapriltag.so /usr/local/lib/python3.10/dist-packages/dt_apriltags/

# Install Python packages in one layer
COPY autocalibration/requirements-runtime.txt /tmp/
COPY autocalibration/tools/ondemand_model_loader.py /usr/local/bin/download_models.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements-runtime.txt && \
    chmod +x /usr/local/bin/download_models.py && \
    rm -rf /tmp/requirements-runtime.txt

# Copy built wheels and install them
COPY --from=camcalibration-builder /output/*.whl /tmp/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /tmp/*.whl && \
    rm -rf /tmp/*.whl

# Copy application code (this changes frequently)
COPY autocalibration/src/camcalibration $SCENESCAPE_HOME/
RUN chmod +x $SCENESCAPE_HOME/camcalibration
COPY autocalibration/src/*.py $SCENESCAPE_HOME/
COPY autocalibration/src/camcalibration-init /usr/local/bin/
RUN chmod +x /usr/local/bin/camcalibration-init

# Create a startup script that ensures model directory permissions and checks NetVLAD model
RUN echo '#!/bin/bash\n\
set -e\n\
chown -R $WSUSER:$WSUSER $NETVLAD_MODEL_DIR\n\
if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then\n\
    echo "Checking NetVLAD model..."\n\
    python3 /usr/local/bin/download_models.py\n\
fi\n\
exec "$@"\n' > /usr/local/bin/startup.sh && chmod +x /usr/local/bin/startup.sh

ENTRYPOINT ["/usr/local/bin/startup.sh", "/usr/local/bin/camcalibration-init"]

# ---------- Cam Calibration Test Stage ------------------
# This stage is meant to be used for test execution (not for final runtime)
FROM camcalibration-runtime AS camcalibration-test
ENV DEBIAN_FRONTEND=noninteractive
ENV SKIP_MODEL_DOWNLOAD=1

# Install Python test dependencies
RUN pip3 install --upgrade --no-cache-dir coverage pytest

RUN : \
    ; eval WSHOME=~$WSUSER \
    ;
