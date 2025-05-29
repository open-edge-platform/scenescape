# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# Copyright (C) 2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

# -------- Build Stage --------
FROM ubuntu:22.04 AS build

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

# Install build dependencies
COPY ./percebro/requirements-buildtime.txt /tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake \
        curl \
        ffmpeg \
        g++ \
        git \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-tools \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libboost-python-dev \
        libegl1 \
        libeigen3-dev \
        libgl1 \
        libglib2.0 \
        libgomp1 \
        libgstreamer-plugins-base1.0-dev \
        libgstreamer1.0-dev \
        libswscale-dev \
        libgtest-dev \
        libtesseract-dev \
        libva-dev \
        make \
        mesa-utils \
        netbase \
        pybind11-dev \
        python-is-python3 \
        python3-dev \
        python3-pip \
        python3-scipy \
        python3-termcolor \
        sudo \
        tesseract-ocr \
        v4l-utils  \
    && pip3 install --upgrade --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /tmp/requirements-buildtime.txt && \
    pip3 uninstall -y openvino-telemetry && \
    rm -rf /tmp/requirements-buildtime.txt && \
    rm -rf /var/lib/apt/lists/*

# Install openvino GPU drivers
RUN : \
    ; TMP=/tmp/intel-gpu.$$ ; mkdir ${TMP} ; cd ${TMP} \
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
    ; dpkg -i ./*.deb \
    ; cd ; rm -rf ${TMP} \
    ; ldconfig \
    ;

RUN if [ "${FORCE_VAAPI}" != "1" ]; then \
        apt-get update && apt-get install -y pciutils; \
        HAS_CARD=$(lspci | grep VGA | grep Intel || true); \
        if [ -z "${HAS_CARD}" ]; then \
            echo "No Intel GPU detected .."; \
            exit 0; \
        fi; \
        echo "Intel GPU detected."; \
    else \
        echo "Forcing VAAPI build."; \
    fi; \
    echo "Setting up video decoding using VAAPI subsystem.."; \
    set -e; \
    RUNTIME_DEPS='intel-gpu-tools libdrm-dev libx11-xcb-dev libxcb-dri3-dev libxfixes-dev libxext-dev'; \
    BUILD_DEPS='autoconf automake autotools-dev bison flex libgnutls28-dev libtool nasm ninja-build'; \
    WDIR=/tmp; \
    TARGET_PREFIX=/usr; \
    TARGET_LIBDIR=${TARGET_PREFIX}/lib/x86_64-linux-gnu; \
    TARGET_INCDIR=${TARGET_PREFIX}/include/x86_64-linux-gnu; \
    apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS $RUNTIME_DEPS; \
    cd ${WDIR}; \
    git clone https://github.com/intel/libva.git && cd libva; \
    ./autogen.sh --prefix=${TARGET_PREFIX} --libdir=${TARGET_LIBDIR} --enable-x11; \
    make && make install; \
    cd ${WDIR}; \
    git clone https://github.com/intel/gmmlib.git && cd gmmlib; \
    mkdir build && cd build; \
    cmake -DCMAKE_BUILD_TYPE=Release -DARCH=64 ..; \
    make -j"$(nproc)" && make install; \
    cd ${WDIR}; \
    git clone https://github.com/intel/media-driver.git; \
    mkdir build_media && cd build_media; \
    cmake ../media-driver; \
    make -j"$(nproc)" && make install; \
    cd ${WDIR} && rm -rf libva gmmlib media-driver build_media; \
    apt-get purge -y $BUILD_DEPS pciutils; \
    rm -rf /var/lib/apt/lists/*

# Build opencv from source and install wheel
RUN : \
    ; CV_URL=https://github.com/opencv/opencv \
    ; CV_VERSION=$(curl -sL -o /dev/null -w '%{url_effective}' "${CV_URL}/releases/latest" | sed -e 's,.*/,,') \
    ; TMP=/tmp/opencv.$$ \
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
    ; MEDIASDK="-DWITH_MFX=OFF" \
    ; mkdir -p build \
    ; cd build \
    ; cmake \
        -DPYTHON3_PACKAGES_PATH="/usr/local/lib/$(find /usr/local/lib -maxdepth 1 -name "python3*" -printf "%f\n")/dist-packages/" \
        -DOPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules \
        -DBUILD_TESTS=OFF \
        -DBUILD_TBB=OFF \
        -DWITH_TBB=OFF \
        -DWITH_OPENGL=ON \
        -DWITH_QT=ON \
        -DWITH_GTK=OFF \
        -DWITH_INF_ENGINE=OFF \
        -DWITH_TESSERACT=OFF \
        -DBUILD_opencv_python3=ON \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_opencv_apps=OFF \
        -DOPENCV_GENERATE_PKGCONFIG=ON \
        ${MEDIASDK} \
        .. \
    ; BUILD_JOBS=$(nproc) \
    ; if [ ${BUILD_JOBS} -gt 16 ]; then \
        BUILD_JOBS=16 \
    ; fi \
    ; make -j "${BUILD_JOBS}" \
    ; make install \
    ; ldconfig \
    ; PYTHON_VERSION=$( python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}');" ) \
    ; cp CMakeFiles/install/python_loader/cv2/config-${PYTHON_VERSION}.py  python_loader/cv2/config-${PYTHON_VERSION}.py \
    ; cd python_loader \
    ; sed -e "s/package_name = 'opencv'/package_name = 'opencv-python'/" -i setup.py \
    ; python setup.py  bdist_wheel \
    ; cp dist/opencv_python-${CV_VERSION}-py3-none-any.whl /tmp/ \
    ; cd ; rm -rf ${TMP}

# Prepare scene_common for install in runtime
COPY ./scene_common tmp/scene_common

# Build and install scene_common (wheel and fast_geometry)
RUN : \
    ; cd /tmp/scene_common \
    ; pip wheel --no-deps . -w /tmp/scene_common_wheel \
    ; make -C fast_geometry -j $(nproc) all install \
    ;

# -------- Runtime Stage --------
FROM ubuntu:22.04 AS runtime


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
# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-tools \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libegl1 \
        libgl1 \
        libglib2.0 \
        libgomp1 \
        libtesseract-dev \
        libva-dev \
        mesa-utils \
        netbase \
        python-is-python3 \
        python3-pip \
        python3-scipy \
        python3-termcolor \
        sudo \
        tesseract-ocr \
        v4l-utils \
        intel-gpu-tools \
        libdrm-dev \
        libx11-xcb-dev \
        libxcb-dri3-dev \
        libxfixes-dev \
        libxext-dev \
    && pip3 install --upgrade --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /tmp/requirements-runtime.txt && \
    pip3 uninstall -y openvino-telemetry && \
    rm -rf /tmp/requirements-runtime.txt && \
    rm -rf /var/lib/apt/lists/*

# # Copy OpenVINO GPU libva gmmlib media-driver drivers from build stage
COPY --from=build /usr/lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/
COPY --from=build /usr/local/lib/ /usr/local/lib/
COPY --from=build /etc/OpenCL/ /etc/OpenCL/
COPY --from=build /etc/ld.so.conf.d/ /etc/ld.so.conf.d/
COPY --from=build /usr/include/x86_64-linux-gnu/   /usr/include/x86_64-linux-gnu/

# Copy OpenCV wheel and install
COPY --from=build /tmp/opencv_python-*-py3-none-any.whl /tmp/
RUN pip3 install --no-cache-dir /tmp/opencv_python-*-py3-none-any.whl && rm /tmp/opencv_python-*-py3-none-any.whl

# Copy and install scene_common wheel
COPY --from=build /tmp/scene_common_wheel/ /tmp/scene_common_wheel/
RUN pip3 install --no-cache-dir /tmp/scene_common_wheel/*.whl && rm -rf /tmp/scene_common_wheel

# Add percebro
COPY ./percebro/src/* $SCENESCAPE_HOME/percebro/
COPY ./utils/waitforbroker $SCENESCAPE_HOME/percebro/utils/
COPY ./percebro/config/model-config.json $SCENESCAPE_HOME/percebro/
# Set correct permisions
RUN chown -R $WSUSER:$WSUSER $SCENESCAPE_HOME/percebro/ && chmod +x $SCENESCAPE_HOME/percebro/percebro

# Copy init scripts
COPY ./percebro/src/percebro-init /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/percebro-init"]
