# =========================
# STAGE 1: BUILD STAGE
# =========================
FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}

# Upgrade pip and install buildtime requirements
COPY autocalibration/requirements-buildtime.txt /tmp/
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake make g++ python3-dev python3-pip python-is-python3 \
    pybind11-dev libeigen3-dev libgtest-dev curl git && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --upgrade --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements-buildtime.txt

# === AprilTag Build and Wheel ===
RUN mkdir -p /output /tmp/apriltag_build /tmp/apriltag && \
    git clone https://github.com/duckietown/lib-dt-apriltags.git /tmp/apriltag/apriltag-dev && \
    cd /tmp/apriltag/apriltag-dev && git submodule update --init && \
    mkdir build && cd build && cmake ../apriltags/ && make -j$(nproc) && \
    cd .. && python3 setup.py bdist_wheel && \
    cp build/*.so /tmp/apriltag_build/ && cp dist/*.whl /output/

# === NetVLAD Weights Build and Wheel ===
RUN mkdir -p /tmp/netvlad/third_party/netvlad && cd /tmp/netvlad && \
    touch third_party/__init__.py third_party/netvlad/__init__.py && \
    curl -Lo third_party/netvlad/VGG16-NetVLAD-Pitts30K.mat \
    https://cvg-data.inf.ethz.ch/hloc/netvlad/Pitts30K_struct.mat && \
    echo "include third_party/netvlad/*" > MANIFEST.in && \
    echo "from setuptools import setup, find_packages\n\
setup(name='third_party', version='1.0.0', packages=find_packages(),\n\
package_data={'': ['VGG16-NetVLAD-Pitts30K.mat']}, include_package_data=True)" > setup.py && \
    python3 setup.py bdist_wheel && cp dist/*.whl /output/

# === reloc wheel build ===
COPY autocalibration/src/reloc /tmp/reloc
RUN cd /tmp/reloc && python3 setup.py bdist_wheel && \
    cp dist/*.whl /output/

# === scene_common build ===
COPY scene_common /tmp/scene_common
RUN cd /tmp/scene_common && \
    pip3 install . && \
    make -C fast_geometry -j$(nproc) all install && \
    cp -r /tmp/scene_common /output/scene_common

# =========================
# STAGE 2: RUNTIME STAGE
# =========================
FROM ubuntu:22.04

ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}
ENV DEBIAN_FRONTEND=noninteractive
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

# Install runtime dependencies
COPY autocalibration/requirements-runtime.txt /tmp/
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip bindfs sudo libgl1 libglib2.0 libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --upgrade --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements-runtime.txt

# Create user
RUN useradd -r -m -s /bin/bash $WSUSER && \
    usermod -a -G video,users $WSUSER && \
    HOME_DIR=$(eval echo ~$WSUSER) && \
    chmod a+rX "$HOME_DIR"

# Install all wheels
COPY --from=builder /output/*.whl /tmp/
RUN pip3 install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# Copy AprilTag shared objects
COPY --from=builder /tmp/apriltag_build/*.so /usr/local/lib/python3.10/dist-packages/dt_apriltags/

# Copy scene_common
COPY --from=builder /output/scene_common /opt/scene_common
ENV PYTHONPATH="/opt/scene_common/src:/opt/scene_common/fast_geometry"

# Copy auto calibration sources
COPY autocalibration/src/camcalibration $SCENESCAPE_HOME/
RUN chmod +x $SCENESCAPE_HOME/camcalibration
COPY autocalibration/src/*.py $SCENESCAPE_HOME/
COPY autocalibration/src/camcalibration-init /usr/local/bin/
RUN chmod +x /usr/local/bin/camcalibration-init

ENTRYPOINT ["/usr/local/bin/camcalibration-init"]
