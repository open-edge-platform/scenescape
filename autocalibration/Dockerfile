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
    git cmake build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (these change more frequently)
COPY autocalibration/requirements-buildtime.txt /tmp/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --upgrade --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements-buildtime.txt

# Create directories (this layer rarely changes)
RUN mkdir -p /output /tmp/apriltag_build /tmp/apriltag /tmp/netvlad

# Copy source code (this changes frequently)
COPY autocalibration/src/reloc /tmp/reloc

# Build wheels in parallel (this changes when source or dependencies change)
RUN --mount=type=cache,target=/root/.cache/pip \
    # AprilTag build
    git clone --depth=1 https://github.com/duckietown/lib-dt-apriltags.git /tmp/apriltag/apriltag-dev && \
    cd /tmp/apriltag/apriltag-dev && \
    git submodule update --init && \
    mkdir build && cd build && \
    cmake ../apriltags/ && make -j$(nproc) && \
    cd .. && python3 setup.py bdist_wheel && \
    cp build/*.so /tmp/apriltag_build/ && \
    cp dist/*.whl /output/ & \
    # NetVLAD build
    cd /tmp/netvlad && \
    touch third_party/__init__.py third_party/netvlad/__init__.py && \
    curl -Lo third_party/netvlad/VGG16-NetVLAD-Pitts30K.mat \
    https://cvg-data.inf.ethz.ch/hloc/netvlad/Pitts30K_struct.mat && \
    echo "include third_party/netvlad/*" > MANIFEST.in && \
    echo -e "from setuptools import setup, find_packages\n\
setup(name='third_party', version='1.0.0', packages=find_packages(),\n\
package_data={'': ['VGG16-NetVLAD-Pitts30K.mat']}, include_package_data=True)" > setup.py && \
    python3 setup.py bdist_wheel && \
    cp dist/*.whl /output/ & \
    # Wait for all background processes
    wait

# Build reloc wheel
RUN --mount=type=cache,target=/root/.cache/pip \
    cd /tmp/reloc && \
    python3 setup.py bdist_wheel && \
    cp dist/*.whl /output/

# =========================
# STAGE 2: RUNTIME STAGE
# =========================
# Runtime stage
FROM python:3.10-slim AS runtime

# Define environment variables first
ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}
ENV DEBIAN_FRONTEND=noninteractive
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape
ENV PYTHONPATH="/usr/local/lib/python3.10/dist-packages"

# Install runtime dependencies first (these change less frequently)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    bindfs sudo libgl1 libglib2.0-0 libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Add user (this rarely changes)
RUN useradd -r -m -s /bin/bash $WSUSER && \
    usermod -a -G video,users $WSUSER && \
    chmod a+rX /home/$WSUSER

# Copy scene_common and fast_geometry from builder stage BEFORE installing other packages
COPY --from=camcalibration-builder /usr/local/lib/python3.10/dist-packages/fast_geometry /usr/local/lib/python3.10/dist-packages/fast_geometry
COPY --from=camcalibration-builder /usr/local/lib/python3.10/dist-packages/scene_common /usr/local/lib/python3.10/dist-packages/scene_common

# Copy AprilTag shared library
COPY --from=camcalibration-builder /tmp/apriltag_build/libapriltag.so /usr/local/lib/python3.10/site-packages/dt_apriltags/

# Install Python packages (these change more frequently)
COPY autocalibration/requirements-runtime.txt /tmp/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements-runtime.txt && \
    rm -rf /tmp/requirements-runtime.txt

# Copy built wheels and install them
COPY --from=camcalibration-builder /output/*.whl /tmp/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*.whl

# Copy application code (this changes frequently)
COPY autocalibration/src/camcalibration $SCENESCAPE_HOME/
RUN chmod +x $SCENESCAPE_HOME/camcalibration
COPY autocalibration/src/*.py $SCENESCAPE_HOME/
COPY autocalibration/src/camcalibration-init /usr/local/bin/
RUN chmod +x /usr/local/bin/camcalibration-init

ENTRYPOINT ["/usr/local/bin/camcalibration-init"]
