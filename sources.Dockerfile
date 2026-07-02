# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM debian:13@sha256:d07d1b51c39f51188e60be9b64e6bf769fa94e187f092bc32b91305cfa34ba5a AS source-grabber

RUN echo "deb-src http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    && echo "deb-src http://security.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list \
    && echo "deb-src http://deb.debian.org/debian bookworm-updates main" >> /etc/apt/sources.list \
    && echo "deb-src http://deb.debian.org/debian trixie main contrib non-free non-free-firmware" >> /etc/apt/sources.list
RUN apt-get update && apt-get install -y --no-install-recommends dpkg-dev

WORKDIR /sources/deb
RUN apt-get source --download-only \
    apache2 \
    apache2-bin \
    apache2-data \
    apache2-utils \
    armadillo \
    base-files \
    bash \
    bzip2 \
    cfitsio \
    curl \
    dpkg \
    elfutils \
    fonts-dejavu-core \
    fyba \
    gcc-12 \
    gcc-14 \
    gdal \
    gdbm \
    gdcm \
    geos \
    glib2.0 \
    glibc \
    gosu \
    hdf5 \
    icu \
    jbigkit \
    libcap2 \
    libcurl3-gnutls \
    libcurl4 \
    libdbus-1-3 \
    libde265 \
    libegl-mesa0 \
    libegl1 \
    libevdev2 \
    libfreetype6 \
    libfreexl1 \
    libgbm1 \
    libgcrypt20 \
    libgeotiff5 \
    libgl1 \
    libgl1-mesa-dri \
    libglapi-mesa \
    libglvnd0 \
    libglx-mesa0 \
    libglx0 \
    libgnutls30 \
    libgraphite2-3 \
    libgssapi-krb5-2 \
    libgudev \
    libharfbuzz0b \
    libhdf4 \
    libheif \
    libhwloc15 \
    libinput \
    libk5crypto3 \
    libkml \
    libkrb5-3 \
    libkrb5support0 \
    liblcms2-2 \
    libldap-2.5-0 \
    libltdl7 \
    libnghttp2-14 \
    libnspr4 \
    libnss3 \
    libopengl0 \
    libpciaccess0 \
    libpng16-16 \
    libpq5 \
    libproj25 \
    libqhull-r8.0 \
    librttopo \
    libsasl2-2 \
    libsasl2-modules-db \
    libssl3 \
    libsystemd0 \
    libtbb12 \
    libtbbbind-2-5 \
    libtbbmalloc2 \
    libudev1 \
    liburiparser1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-util1 \
    lm-sensors \
    mariadb \
    mosquitto \
    netcdf \
    numactl \
    ogdi-dfsg \
    opencv \
    openssl \
    perl \
    poppler \
    procps \
    proj-data \
    protobuf \
    python3.11 \
    python3-pip \
    python3-wheel \
    qtbase-opensource-src \
    rtmpdump \
    sed \
    shared-mime-info \
    spatialite \
    superlu \
    unixodbc \
    wget \
    x11-common \
    x265 \
    xerces-c \
    z3

WORKDIR /sources/python
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates git
RUN : \
    ; git clone --depth 1 https://github.com/certifi/python-certifi \
    ; git clone --depth 1 https://github.com/dranjan/python-plyfile \
    ; git clone --depth 1 https://github.com/eclipse-paho/paho.mqtt.python \
    ; git clone --depth 1 https://github.com/ijl/orjson \
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
    ; git clone --depth 1 https://github.com/gcc-mirror/gcc \
    ; git clone --depth 1 https://git.savannah.gnu.org/git/config.git gnu-config

WORKDIR /sources/other
RUN : \
    ; git clone --depth 1 https://github.com/mozilla/geckodriver \
    ; git clone --depth 1 https://github.com/mirror/busybox

FROM debian:13@sha256:d07d1b51c39f51188e60be9b64e6bf769fa94e187f092bc32b91305cfa34ba5a

COPY --from=source-grabber /sources /sources
COPY third-party-programs.txt /sources
WORKDIR /sources

USER nobody
