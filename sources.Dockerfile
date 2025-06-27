# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

FROM ubuntu:22.04 AS source-grabber

RUN echo "deb-src http://archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/sources.list
RUN apt update && apt-get install -y --no-install-recommends dpkg-dev

WORKDIR /sources-deb
RUN apt-get source --download-only \
    apparmor \
    avahi \
    bindfs \
    build-essential \
    ca-certificates \
    cli-common \
    codec2 \
    cryptsetup \
    cups \
    dbus \
    dconf \
    dh-elpa \
    dirmngr \
    elfutils \
    firefox \
    fuse \
    g++ \
    gcc \
    gdk-pixbuf \
    glib2.0 \
    glibc \
    glib-networking \
    gobject-introspection \
    gpm \
    gssdp \
    graphite2 \
    gupnp \
    iso-codes \
    jbigkit-bin \
    json-glib \
    kmod \
    lame \
    libassuan \
    libeigen3-dev \
    libgdbm6 \
    libgraphite2-dev \
    libmpc \
    libmpg123-0 \
    libpango1.0-0 \
    libproxy \
    librsvg \
    libslang2 \
    libssh \
    libudev0 \
    linux \
    lm-sensors \
    lsb \
    lvm2 \
    mailcap \
    media-types \
    mime-support \
    mpfr4 \
    netbase \
    netcat \
    nss-passwords \
    patch \
    pci.ids \
    perl \
    pkg-config \
    pygobject \
    python-datrie \
    python-dbusmock \
    readline \
    rtmpdump \
    shared-mime-info \
    software-properties \
    ssl-cert \
    util-linux \
    what-is-python \
    x11-common

WORKDIR /sources-python
RUN apt-get update && apt-get install -y ca-certificates git
RUN : \
    ; git clone --depth 1 https://github.com/eclipse-paho/paho.mqtt.python \
    ; git clone --depth 1 https://github.com/psycopg/psycopg2 \
    ; git clone --depth 1 https://github.com/pytest-dev/pytest-html \
    ; git clone --depth 1 https://github.com/pytest-dev/pytest-metadata \
    ; git clone --depth 1 https://github.com/certifi/python-certifi \
    ; git clone --depth 1 https://github.com/tqdm/tqdm

WORKDIR /sources-other
RUN : \
    ; git clone --depth 1 https://github.com/mozilla/geckodriver \
    ; git clone --depth 1 https://github.com/eclipse-mosquitto/mosquitto \
    ; git clone --depth 1 https://github.com/mirror/busybox

FROM busybox

COPY --from=source-grabber /sources* /sources
COPY third-party-programs.txt /sources
WORKDIR /sources
