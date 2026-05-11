# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM debian:13@sha256:e2d08da6f42ef4b09b165d55528a12727aeed8240dc9edf888e3ec07e10ef9da AS source-grabber

RUN echo "deb-src http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    && echo "deb-src http://security.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list \
    && echo "deb-src http://deb.debian.org/debian bookworm-updates main" >> /etc/apt/sources.list \
    && echo "deb-src http://deb.debian.org/debian trixie main contrib non-free non-free-firmware" >> /etc/apt/sources.list
RUN apt-get update && apt-get install -y --no-install-recommends dpkg-dev

WORKDIR /sources/deb
RUN apt-get source --download-only \
    armadillo \
    bindfs \
    cfitsio \
    elfutils \
    fuse \
    gcc-12 \
    gcc-14 \
    gdal \
    gdbm \
    gdcm \
    geos \
    glib2.0 \
    glibc \
    libhdf4 \
    hdf5 \
    icu \
    jbigkit \
    json-c \
    libde265 \
    fyba \
    libgudev \
    libheif \
    libinput \
    libkml \
    librttopo \
    libwebp \
    lm-sensors \
    mariadb \
    media-types \
    mosquitto \
    netcdf \
    numactl \
    ogdi-dfsg \
    opencv \
    perl \
    poppler \
    procps \
    protobuf \
    python3.11 \
    qtbase-opensource-src \
    rtmpdump \
    socket++ \
    spatialite \
    superlu \
    unixodbc \
    wget \
    x265 \
    xerces-c \
    z3

WORKDIR /sources/python
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates git
RUN : \
    ; git clone --depth 1 https://github.com/certifi/python-certifi \
    ; git clone --depth 1 https://github.com/dranjan/python-plyfile \
    ; git clone --depth 1 https://github.com/eclipse-paho/paho.mqtt.python \
    ; git clone --depth 1 https://github.com/jab/bidict \
    ; git clone --depth 1 https://github.com/psycopg/psycopg2 \
    ; git clone --depth 1 https://github.com/tqdm/tqdm

WORKDIR /sources/conan
RUN : \
    ; git clone --depth 1 https://github.com/autotools-mirror/autoconf \
    ; git clone --depth 1 https://github.com/autotools-mirror/automake \
    ; git clone --depth 1 https://github.com/autotools-mirror/libtool \
    ; git clone --depth 1 https://github.com/autotools-mirror/m4 \
    ; git clone --depth 1 https://github.com/eclipse/paho.mqtt.c \
    ; git clone --depth 1 https://github.com/eclipse/paho.mqtt.cpp \
    ; git clone --depth 1 https://github.com/eigenteam/eigen-git-mirror \
    ; git clone --depth 1 https://github.com/gcc-mirror/gcc

WORKDIR /sources/other
RUN : \
    ; git clone --depth 1 https://github.com/mozilla/geckodriver \
    ; git clone --depth 1 https://github.com/mirror/busybox

FROM debian:13@sha256:e2d08da6f42ef4b09b165d55528a12727aeed8240dc9edf888e3ec07e10ef9da

COPY --from=source-grabber /sources /sources
COPY third-party-programs.txt /sources
WORKDIR /sources

USER nobody
