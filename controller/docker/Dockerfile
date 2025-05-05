# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# Copyright (C) 2021-2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

FROM ubuntu:22.04

# We use root for runtime init. The command in ENTRYPOINT will drop to an unprivileged user.
# hadolint ignore=DL3002
USER root

SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com

ENV DEBIAN_FRONTEND=noninteractive

# SceneScape requirements #Change this to just controller requirements?
COPY requirements-controller.txt /tmp
RUN : \
    ; apt-get update \
    ; apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        cmake \
        curl \
        g++ \
        git \
        libeigen3-dev \
        libglib2.0-0 \
        libgl1-mesa-glx \
        libgtest-dev \
        make \
        netbase \
        patch \
        pybind11-dev \
        python-is-python3 \
        python3-pip \
        python3-scipy \
        sudo \
    ; apt-get purge -y python3-numpy \
    ; pip3 install --upgrade --no-cache-dir \
        -r /tmp/requirements-controller.txt \
    ; rm -rf /tmp/requirements-controller.txt \
    ;

ENV WSUSER=scenescape

RUN : \
    ; useradd -r -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;

ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

# Install opencv
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
    -DWITH_GSTREAMER=OFF \
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
; pip install dist/opencv_python-${CV_VERSION}-py3-none-any.whl \
; cd ; rm -rf ${TMP}

# Install robot vision package
ADD robot_vision.tar /tmp/
RUN : \
    ; export OpenCV_DIR="/opt/intel/openvino/extras/opencv" \
    ; cd /tmp/robot_vision \
    ; python3 setup.py bdist_wheel \
    ; cd dist \
    ; pip3 install --no-cache-dir ./*.whl \
    ; cd \
    ; rm -rf /tmp/robot_vision \
    ;

# Install scene common
ADD scene_common.tar tmp/
RUN : \
    ; cd tmp/scene_common \
    ; pip install --no-cache-dir . \
    ; make -C fast_geometry -j $(nproc) all install \
    ; cd .. \
    ; rm -rf scene_common \
    ;

ADD controller.tar $SCENESCAPE_HOME/
RUN : \
    ; eval WSHOME=~$WSUSER \
    ; chown -R "$WSUSER" "$SCENESCAPE_HOME" \
    ; pip3 install --no-cache-dir "$SCENESCAPE_HOME/" \
    ;

RUN : \
    ; apt-get purge -y --auto-remove make cmake git \
    ; apt-get clean \
    ; rm -rf /var/lib/apt/lists/* \
    ;

COPY controller-init /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/controller-init"]
