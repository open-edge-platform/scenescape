# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM debian:13@sha256:f324c7ff54321e8d9c588493a20244965938ce0aa50bbd1022d38010e9ffc4b1 AS source-grabber

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
    bzip2 \
    ca-certificates \
    cfitsio \
    curl \
    elfutils \
    ffmpeg \
    fonts-dejavu-core \
    fyba \
    gcc-12 \
    gcc-14 \
    gdal \
    gdbm \
    gdcm \
    geos \
    git \
    git-man \
    glib2.0 \
    glibc \
    gosu \
    hdf5 \
    icu \
    jbigkit \
    libarchive13 \
    libasound2 \
    libasound2-data \
    libass9 \
    libasyncns0 \
    libavc1394-0 \
    libavcodec59 \
    libavdevice59 \
    libavfilter8 \
    libavformat59 \
    libavutil57 \
    libbluray2 \
    libbs2b0 \
    libcaca0 \
    libcairo-gobject2 \
    libcairo2 \
    libcdio-cdda2 \
    libcdio-paranoia2 \
    libcdio19 \
    libchromaprint1 \
    libcodec2-1.0 \
    libcurl3-gnutls \
    libcurl4 \
    libdatrie1 \
    libdbus-1-3 \
    libdc1394-25 \
    libde265 \
    libdecor-0-0 \
    libegl-mesa0 \
    libegl1 \
    liberror-perl \
    libevdev2 \
    libflac12 \
    libflite1 \
    libfreetype6 \
    libfreexl1 \
    libfribidi0 \
    libgbm1 \
    libgdk-pixbuf-2.0-0 \
    libgdk-pixbuf2.0-common \
    libgeotiff5 \
    libgl1 \
    libgl1-mesa-dri \
    libglapi-mesa \
    libglvnd0 \
    libglx-mesa0 \
    libglx0 \
    libgme0 \
    libgraphite2-3 \
    libgudev \
    libharfbuzz0b \
    libhdf4 \
    libheif \
    libhwloc15 \
    libiec61883-0 \
    libinput \
    libjack-jackd2-0 \
    libkml \
    liblcms2-2 \
    libldap-2.5-0 \
    libltdl7 \
    libmbedcrypto7 \
    libmp3lame0 \
    libmpg123-0 \
    libnghttp2-14 \
    libnspr4 \
    libnss3 \
    libopenal-data \
    libopenal1 \
    libopengl0 \
    libopenmpt0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libpciaccess0 \
    libpgm-5.3-0 \
    libplacebo208 \
    libpng16-16 \
    libpocketsphinx3 \
    libpostproc56 \
    libpq5 \
    libproj25 \
    libpulse0 \
    libqhull-r8.0 \
    libraw1394-11 \
    librsvg2-2 \
    librttopo \
    librubberband2 \
    libsamplerate0 \
    libsasl2-2 \
    libsasl2-modules-db \
    libsdl2-2.0-0 \
    libshine3 \
    libslang2 \
    libsndfile1 \
    libsodium23 \
    libsoxr0 \
    libspeex1 \
    libsphinxbase3 \
    libsrt1.5-gnutls \
    libssh-gcrypt-4 \
    libsvtav1enc1 \
    libswresample4 \
    libswscale6 \
    libtbb12 \
    libtbbbind-2-5 \
    libtbbmalloc2 \
    libthai-data \
    libthai0 \
    libtwolame0 \
    libudfread0 \
    liburiparser1 \
    libusb-1.0-0 \
    libva-drm2 \
    libva-x11-2 \
    libva2 \
    libvidstab1.1 \
    libx264-164 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-util1 \
    libxvidcore4 \
    libzimg2 \
    libzmq5 \
    libzvbi-common \
    libzvbi0 \
    lm-sensors \
    mariadb \
    mosquitto \
    netcdf \
    numactl \
    ogdi-dfsg \
    opencv \
    perl \
    poppler \
    procps \
    proj-data \
    protobuf \
    python3-pip \
    python3-wheel \
    python3.11 \
    qtbase-opensource-src \
    rtmpdump \
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
    ; git clone --depth 1 https://github.com/gcc-mirror/gcc

WORKDIR /sources/other
RUN : \
    ; git clone --depth 1 https://github.com/mozilla/geckodriver \
    ; git clone --depth 1 https://github.com/mirror/busybox

FROM debian:13@sha256:f324c7ff54321e8d9c588493a20244965938ce0aa50bbd1022d38010e9ffc4b1

COPY --from=source-grabber /sources /sources
COPY third-party-programs.txt /sources
WORKDIR /sources

USER nobody
