# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-FileCopyrightText: 2018 Ignacio Gómez
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

ARG MOSQUITTO_VERSION=2.0.18
# Define libwebsocket version
ARG LWS_VERSION=4.2.2

# Use debian:stable-slim as a builder for Mosquitto and dependencies.
FROM debian:stable-slim AS mosquitto_builder
ARG MOSQUITTO_VERSION
ARG LWS_VERSION

# Get mosquitto build dependencies.
RUN set -ex; \
    apt-get update; \
    apt-get install -y wget build-essential cmake libssl-dev libcjson-dev; \
    wget https://github.com/warmcat/libwebsockets/archive/v${LWS_VERSION}.tar.gz -O /tmp/lws.tar.gz; \
    mkdir -p /build/lws; \
    tar --strip=1 -xf /tmp/lws.tar.gz -C /build/lws; \
    rm /tmp/lws.tar.gz; \
    cd /build/lws; \
    cmake . \
        -DCMAKE_BUILD_TYPE=MinSizeRel \
        -DCMAKE_INSTALL_PREFIX=/usr \
        -DLWS_IPV6=ON \
        -DLWS_WITHOUT_BUILTIN_GETIFADDRS=ON \
        -DLWS_WITHOUT_CLIENT=ON \
        -DLWS_WITHOUT_EXTENSIONS=ON \
        -DLWS_WITHOUT_TESTAPPS=ON \
        -DLWS_WITH_HTTP2=OFF \
        -DLWS_WITH_SHARED=OFF \
        -DLWS_WITH_ZIP_FOPS=OFF \
        -DLWS_WITH_ZLIB=OFF \
        -DLWS_WITH_EXTERNAL_POLL=ON; \
    make -j "$(nproc)"; \
    make install; \
    rm -rf /build/lws /root/.cmake;

WORKDIR /app

RUN mkdir -p mosquitto/auth mosquitto/conf.d && \
    wget http://mosquitto.org/files/source/mosquitto-${MOSQUITTO_VERSION}.tar.gz && \
    tar xzvf mosquitto-${MOSQUITTO_VERSION}.tar.gz && \
    cd mosquitto-${MOSQUITTO_VERSION} && \
    make CFLAGS="-Wall -O2 -I/build/lws/include" LDFLAGS="-L/build/lws/lib" WITH_WEBSOCKETS=yes && \
    make install && \
    cd /app && \
    rm -rf mosquitto-${MOSQUITTO_VERSION} mosquitto-${MOSQUITTO_VERSION}.tar.gz; \
    apt-get purge -y --auto-remove \
      wget \
      build-essential \
      cmake; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Use golang:latest as a builder for the Mosquitto Go Auth plugin.
FROM --platform=$BUILDPLATFORM golang:latest AS go_auth_builder

ENV CGO_CFLAGS="-I/usr/local/include -fPIC"
ENV CGO_LDFLAGS="-shared -Wl,-unresolved-symbols=ignore-all"
ENV CGO_ENABLED=1

# Bring TARGETPLATFORM to the build scope
ARG TARGETPLATFORM
ARG BUILDPLATFORM

# Install TARGETPLATFORM parser to translate its value to GOOS, GOARCH, and GOARM
COPY --from=tonistiigi/xx:golang / /
RUN go env; \
  if [ ! -z "$TARGETPLATFORM" ]; then \
    case "$TARGETPLATFORM" in \
  "linux/arm64") \
    apt update && apt install -y gcc-aarch64-linux-gnu libc6-dev-arm64-cross \
    ;; \
  "linux/arm/v7") \
    apt update && apt install -y gcc-arm-linux-gnueabihf libc6-dev-armhf-cross \
    ;; \
  "linux/arm/v6") \
    apt update && apt install -y gcc-arm-linux-gnueabihf libc6-dev-armel-cross libc6-dev-armhf-cross \
    ;; \
  esac \
  fi

WORKDIR /app
COPY --from=mosquitto_builder /usr/local/include/ /usr/local/include/

RUN git clone --depth 1 https://github.com/iegomez/mosquitto-go-auth.git /app && \
    cd /app && \
    go mod edit -require=golang.org/x/crypto@v0.38.0 && \
    go mod tidy && \
    go build -buildmode=c-archive go-auth.go && \
    go build -buildmode=c-shared -o go-auth.so && \
    go build pw-gen/pw.go

#Start from a new image.
FROM debian:stable-slim

RUN set -ex; \
    apt update; \
    apt install -y libc-ares2 openssl uuid tini libssl-dev libcjson-dev; \
    mkdir -p /var/lib/mosquitto /var/log/mosquitto; \
    groupadd mosquitto; \
    useradd -s /sbin/nologin mosquitto -g mosquitto -d /var/lib/mosquitto; \
    chown -R mosquitto:mosquitto /var/log/mosquitto/; \
    chown -R mosquitto:mosquitto /var/lib/mosquitto/

#Copy confs, plugin so and mosquitto binary.
COPY --from=mosquitto_builder /app/mosquitto/ /mosquitto/
COPY --from=go_auth_builder /app/pw /mosquitto/pw
COPY --from=go_auth_builder /app/go-auth.so /mosquitto/go-auth.so
COPY --from=mosquitto_builder /usr/local/sbin/mosquitto /usr/sbin/mosquitto

COPY --from=mosquitto_builder /usr/local/lib/libmosquitto* /usr/local/lib/

COPY --from=mosquitto_builder /usr/local/bin/mosquitto_passwd /usr/bin/mosquitto_passwd
COPY --from=mosquitto_builder /usr/local/bin/mosquitto_sub /usr/bin/mosquitto_sub
COPY --from=mosquitto_builder /usr/local/bin/mosquitto_pub /usr/bin/mosquitto_pub
COPY --from=mosquitto_builder /usr/local/bin/mosquitto_rr /usr/bin/mosquitto_rr

RUN ldconfig;

RUN <<EOCMD
cat > /usr/local/sbin/broker-init <<EOF
#!/bin/bash

set -e

RUNSECRETS=/run/secrets

# Change auth_opt_http_host in mosquitto.conf to be dynamic, if REST_SERVER is set
if [ -n "\${REST_SERVER}" ] ; then
    echo Changing http host address to \${REST_SERVER}
    sed -i "s/web.scenescape.intel.com/\${REST_SERVER}/g" /etc/mosquitto/mosquitto.conf
fi

cp \${RUNSECRETS}/scenescape-broker.key \${RUNSECRETS}/scenescape-broker.crt /etc/mosquitto/
chown mosquitto:mosquitto /etc/mosquitto/scenescape-broker.key
echo "Container is ready"
# for kubernetes readinessProbe
touch /tmp/healthy
/usr/sbin/mosquitto -c /etc/mosquitto/mosquitto.conf
EOF
chmod a+x /usr/local/sbin/broker-init
EOCMD

RUN <<EOCMD
mkdir -p /etc/mosquitto
cat > /etc/mosquitto/mosquitto.conf <<EOF
log_dest stderr

allow_anonymous false

auth_plugin /mosquitto/go-auth.so
auth_opt_backends http
auth_opt_http_port 443
auth_opt_http_with_tls true
auth_opt_check_prefix false

auth_opt_http_host web.scenescape.intel.com
auth_opt_http_getuser_uri /api/v1/auth
auth_opt_http_aclcheck_uri /api/v1/aclcheck
auth_opt_http_response_mode status
auth_opt_http_params_mode form
auth_opt_retry_count 9
auth_opt_log_level warn
auth_opt_cache true
auth_opt_acl_cache_seconds 3600

listener 1883
keyfile /etc/mosquitto/scenescape-broker.key
certfile /etc/mosquitto/scenescape-broker.crt
tls_version tlsv1.3

listener 1884
keyfile /etc/mosquitto/scenescape-broker.key
certfile /etc/mosquitto/scenescape-broker.crt
protocol websockets

max_packet_size 104857600
max_connections 500
sys_interval 0
EOF
EOCMD

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/sbin/broker-init"]
