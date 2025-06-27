# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

# -------- Build Stage --------
FROM scenescape-common-base AS percebro-builder

SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com

ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

ENV DEBIAN_FRONTEND=noninteractive
ARG FORCE_VAAPI

# Add scenescape user
RUN : \
    ; useradd -r -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;

RUN export no_proxy= \
    && apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gpg \
    && wget --no-check-certificate -qO- https://repositories.intel.com/gpu/intel-graphics.key | \
    gpg --dearmor --output /usr/share/keyrings/gpu-intel-graphics.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/gpu-intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy client" | \
    tee /etc/apt/sources.list.d/intel-gpu-"${VERSION_CODENAME}".list

# Install build dependencies
RUN export no_proxy= \
    && apt-get update && apt-get install -y --no-install-recommends \
        checkinstall \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libboost-python-dev \
        libegl1 \
        libgl1 \
        libglib2.0 \
        libgomp1 \
        libgstreamer-plugins-base1.0-dev \
        libgstreamer1.0-dev \
        libswscale-dev \
        libtesseract-dev \
        libx11-dev \
        libx11-xcb-dev \
        libxcb-dri3-dev \
        libxext-dev \
        libxfixes-dev \
        python3-dev \
        intel-media-va-driver-non-free \
        libva-dev \
        libdrm-dev \
    && pip3 install --upgrade --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        pybind11 \
    && rm -rf /var/lib/apt/lists/*

# Install openvino GPU drivers
RUN : \
    ; TMP=/tmp/intel-gpu ; mkdir ${TMP} ; cd ${TMP} \
    ; downloadGPU() { curl -L -O -J "${RELDIR}/$1" ; } \
    ; RELEASE=24.35.30872.22 \
    ; SUBVER=1.3.30872.22 \
    ; IGC_VER=1.0.17537.20 \
    ; IGDGMM_VER=22.5.0 \
    ; RELDIR=https://github.com/intel/compute-runtime/releases/download/${RELEASE} \
    ; downloadGPU intel-level-zero-gpu-dbgsym_${SUBVER}_amd64.ddeb \
    ; downloadGPU intel-level-zero-gpu-legacy1-dbgsym_${SUBVER}_amd64.ddeb \
    ; downloadGPU intel-level-zero-gpu_${SUBVER}_amd64.deb \
    ; downloadGPU intel-level-zero-gpu-legacy1_${SUBVER}_amd64.deb \
    ; downloadGPU intel-opencl-icd-dbgsym_${RELEASE}_amd64.ddeb \
    ; downloadGPU intel-opencl-icd-legacy1-dbgsym_${RELEASE}_amd64.ddeb \
    ; downloadGPU intel-opencl-icd_${RELEASE}_amd64.deb \
    ; downloadGPU intel-opencl-icd-legacy1_${RELEASE}_amd64.deb \
    ; downloadGPU libigdgmm12_${IGDGMM_VER}_amd64.deb \
    ; RELDIR=https://github.com/intel/intel-graphics-compiler/releases/download/igc-${IGC_VER} \
    ; downloadGPU intel-igc-core_${IGC_VER}_amd64.deb \
    ; downloadGPU intel-igc-opencl_${IGC_VER}_amd64.deb \
    ; dpkg -i *.deb \
    ; ldconfig \
    ;

# Build opencv from source and install wheel
RUN : \
    ; CV_URL=https://github.com/opencv/opencv \
    ; CV_VERSION=$(curl -sL -o /dev/null -w '%{url_effective}' "${CV_URL}/releases/latest" | sed -e 's,.*/,,') \
    ; TMP=/tmp/opencv.$$ \
    ; mkdir -p /tmp/debs \
    ; mkdir ${TMP} \
    ; cd ${TMP} \
    ; if [ ! -d opencv_contrib ] ; then \
        git clone --depth 1 -b ${CV_VERSION} ${CV_URL}_contrib.git \
    ; fi \
    ; cd opencv_contrib \
    ; CV_VERSION=$(git symbolic-ref -q --short HEAD || git describe --tags --exact-match) \
    ; cd .. \
    ; if [ ! -d opencv ] ; then \
        git clone --depth 1 -b ${CV_VERSION} ${CV_URL}.git \
    ; fi \
    ; cd opencv \
    ; mkdir -p build \
    ; cd build \
    ; cmake \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DPYTHON3_PACKAGES_PATH="/usr/local/lib/$(find /usr/local/lib -maxdepth 1 -name "python3*" -printf "%f\n")/dist-packages/" \
        -DOPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules \
        -DBUILD_TESTS=OFF \
        -DBUILD_TBB=OFF \
        -DWITH_TBB=OFF \
        -DWITH_OPENGL=ON \
        -DWITH_QT=OFF \
        -DWITH_GTK=OFF \
        -DWITH_INF_ENGINE=OFF \
        -DWITH_TESSERACT=OFF \
        -DBUILD_opencv_python3=ON \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_opencv_apps=OFF \
        -DOPENCV_GENERATE_PKGCONFIG=ON \
        -DWITH_VA=ON \
        -DWITH_VA_INTEL=ON \
        -DWITH_MFX=OFF \
        .. \
    ; make -j $(nproc) \
    ; checkinstall \
    ; ldconfig \
    ; cp ${TMP}/opencv/build/*.deb /tmp/debs/ \
    ; PYTHON_VERSION=$( python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}');" ) \
    ; cp CMakeFiles/install/python_loader/cv2/config-${PYTHON_VERSION}.py  python_loader/cv2/config-${PYTHON_VERSION}.py \
    ; cd python_loader \
    ; sed -e "s/package_name = 'opencv'/package_name = 'opencv-python'/" -i setup.py \
    ; python setup.py  bdist_wheel \
    ; cp dist/opencv_python-${CV_VERSION}-py3-none-any.whl /tmp/ \
    ; cd ; rm -rf ${TMP}

# -------- Runtime Stage --------
FROM ubuntu:22.04 AS percebro-runtime


SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com

ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

ENV DEBIAN_FRONTEND=noninteractive
ARG FORCE_VAAPI

# Add scenescape user
RUN : \
    ; useradd -r -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;
COPY ./percebro/requirements-runtime.txt /tmp

# Copy Intel GPU repository configuration from builder image
COPY --from=percebro-builder /etc/apt/sources.list.d/intel-gpu-*.list /etc/apt/sources.list.d/
COPY --from=percebro-builder /usr/share/keyrings/gpu-intel-graphics.gpg /usr/share/keyrings/

# Install runtime dependencies only
RUN export no_proxy= && \
    apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-tools \
        intel-gpu-tools \
        libegl1 \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libavcodec58 \
        libavformat58 \
        libswscale5 \
        libtesseract4 \
        libx11-xcb1 \
        libxcb-dri3-0 \
        libxext6 \
        libxfixes3 \
        libdrm2 \
        libva2 \
        mesa-utils \
        netbase \
        python-is-python3 \
        python3-pip \
        sudo \
        tesseract-ocr \
        v4l-utils \
        intel-media-va-driver-non-free \
    && pip3 install --upgrade --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /tmp/requirements-runtime.txt && \
    pip3 uninstall -y openvino-telemetry && \
    rm -rf /tmp/requirements-runtime.txt && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy GPU driver debs
COPY --from=percebro-builder /tmp/intel-gpu/*.deb /tmp/
RUN dpkg -i --force-overwrite /tmp/*.deb; \
    rm -f /tmp/*.deb

# Copy OpenCV wheel and install
COPY --from=percebro-builder /tmp/debs/*.deb /tmp/opencv_python-*-py3-none-any.whl /tmp/
RUN dpkg -i --force-overwrite /tmp/*.deb; \
    pip3 install --no-cache-dir /tmp/opencv_python-*-py3-none-any.whl && rm /tmp/opencv_python-*-py3-none-any.whl; \
    rm -rf /tmp

# Copy scene_common
COPY --from=percebro-builder /usr/local/lib/python3.10/dist-packages/fast_geometry /usr/local/lib/python3.10/dist-packages/fast_geometry
COPY --from=percebro-builder /usr/local/lib/python3.10/dist-packages/scene_common /usr/local/lib/python3.10/dist-packages/scene_common

# Add percebro
COPY ./percebro/src/* $SCENESCAPE_HOME/percebro/
COPY ./percebro/src/beancount.sh $SCENESCAPE_HOME/percebro/
COPY ./percebro/src/model-config.json $SCENESCAPE_HOME/percebro/
COPY ./tools/waitforbroker $SCENESCAPE_HOME/percebro/tools/
COPY ./percebro/config/model-config.json $SCENESCAPE_HOME/percebro/
# Set correct permisions
RUN chown -R $WSUSER:$WSUSER $SCENESCAPE_HOME/percebro/ && chmod +x $SCENESCAPE_HOME/percebro/percebro

ENV LIBVA_DRIVER_NAME=iHD
ENV LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri
ENV OPENCV_FFMPEG_DEBUG=1

# Copy init scripts
COPY ./percebro/src/percebro-init /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/percebro-init"]

# ---------- Percebro Test Stage ------------------
# This stage is meant to be used for test execution (not for final runtime)
FROM percebro-runtime AS percebro-test
ENV DEBIAN_FRONTEND=noninteractive

# Install Python test dependencies
RUN pip3 install --upgrade --no-cache-dir coverage pytest

RUN : \
    ; eval WSHOME=~$WSUSER \
    ;
