# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM ubuntu:22.04 AS source-grabber

RUN echo "deb-src http://archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/sources.list
RUN apt update && apt-get install -y --no-install-recommends dpkg-dev

WORKDIR /sources-deb
RUN apt-get source --download-only \
    bindfs \
    ca-certificates \
    fuse \
    geos \
    libapparmor1 \
    libdbus-1-3 \
    libde265-0 \
    libelf1 \
    libfuse2 \
    libfyba0 \
    libgdbm-compat4 \
    libgdbm6 \
    libgfortran5 \
    libglib2.0-0 \
    libgomp1 \
    libgraphite2-3 \
    libgudev-1.0-0 \
    libheif1 \
    libinput-bin \
    libinput10 \
    libio-pty-perl \
    libjson-c5 \
    liblapack3 \
    libmysqlclient21 \
    libodbc2 \
    libodbcinst2 \
    libogdi4.1 \
    libreadline8 \
    librtmp1 \
    librttopo1 \
    libsensors-config \
    libsensors5 \
    libsocket++1 \
    libssh-4 \
    libtirpc-common \
    libvulkan1 \
    libwebp7 \
    libwebpmux3 \
    locales \
    make \
    media-types \
    mysql-common \
    netbase \
    poppler \
    publicsuffix \
    python-is-python3 \
    qtbase-opensource-src \
    readline-common \
    spatialite \
    ssl-cert \
    ucf \
    unixodbc-common \
    wget

WORKDIR /sources-python
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates git
RUN : \
    ; git clone --depth 1 https://github.com/eclipse-paho/paho.mqtt.python \
    ; git clone --depth 1 https://github.com/psycopg/psycopg2 \
    ; git clone --depth 1 https://github.com/certifi/python-certifi \
    ; git clone --depth 1 https://github.com/tqdm/tqdm

WORKDIR /sources-other
RUN : \
    ; git clone --depth 1 https://github.com/mozilla/geckodriver \
    ; git clone --depth 1 https://github.com/mirror/busybox

FROM ubuntu:24.04

COPY --from=source-grabber /sources* /sources
COPY third-party-programs.txt /sources
WORKDIR /sources

USER ubuntu
