#!/bin/sh

# Copyright (C) 2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

if [ "${FORCE_VAAPI}" != "1" ]
then
  apt-get update && apt-get install -y pciutils
  HAS_CARD=$( lspci | grep VGA | grep Intel )
  if [ -z "${HAS_CARD}" ]
  then
    echo "No Intel GPU detected .."
    exit 0
  fi
  echo "Intel GPU detected."
else
  echo "Forcing VAAPI build."
fi

echo "Setting up video decoding using VAAPI subsystem.."

#Abort on any failure.
set -e

# Install dependencies : apt-get installed
# The following are dependencies needed at runtime by ffmpeg / gstreamer
RUNTIME_DEPS="intel-gpu-tools \
        libdrm-dev \
        libx11-xcb-dev \
        libxcb-dri3-dev \
        libxfixes-dev \
        libxext-dev"
# The following are dependencies needed at build time, will be removed later.
BUILD_DEPS="autoconf \
        automake \
        autotools-dev \
        bison \
        flex \
        libgnutls28-dev \
        libtool \
        nasm \
        ninja-build"

# Work and Install directories
WDIR=/tmp
TARGET_PREFIX=/usr
TARGET_LIBDIR=${TARGET_PREFIX}/lib/x86_64-linux-gnu
TARGET_INCDIR=${TARGET_INCDIR}/include/x86_64-linux-gnu

## 0: Install build-time dependencies
apt-get update && apt-get install -y --no-install-recommends ${BUILD_DEPS} ${RUNTIME_DEPS}

## 1: Build latest libva + media-driver.
## 1.1: libva
cd ${WDIR}
git clone https://github.com/intel/libva.git && cd libva
./autogen.sh --prefix=${TARGET_PREFIX} --libdir=${TARGET_LIBDIR} --enable-x11
make && make install
## 1.3: gmmlib
cd ${WDIR}
git clone https://github.com/intel/gmmlib.git && cd gmmlib
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release -DARCH=64  ..
make -j"$(nproc)"&&  make install
## 1.3: media-driver
cd ${WDIR}
git clone https://github.com/intel/media-driver.git
mkdir build_media && cd build_media
cmake ../media-driver
make -j"$(nproc)" && make install
## 1.4: Cleanup
cd ${WDIR} && rm -rf libva gmmlib media-driver build_media

## Remove unnecessary build packages
apt-get purge -y ${BUILD_DEPS} pciutils
rm -rf /var/lib/apt/lists/*
