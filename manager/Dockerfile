# -*- mode: Fundamental; indent-tabs-mode: nil -*-

# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=python:3.14-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f

FROM intel/scenescape-common-base AS scenescape-manager-builder

# We use root for runtime init. The command in ENTRYPOINT will drop to an unprivileged user.
# hadolint ignore=DL3002
USER root
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    libboost-python-dev \
    libegl1 \
    libgl1 \
    libglib2.0 \
    python3-dev \
    libassimp-dev \
    wget \
    libssl3 \
    libssl-dev \
    libpcre2-dev \
    apache2-dev \
    apache2 \
    && rm -rf /var/lib/apt/lists/*

# mod_qos library is broken on debian 12, so we build it from source.
# Use multiple download endpoints and dynamic extraction path to avoid pin-breakage.
ARG MOD_QOS_VERSION=11.79
RUN : \
    ; MOD_QOS_ARCHIVE="/tmp/mod_qos-${MOD_QOS_VERSION}.tar.gz" \
    ; for URL in \
    "https://downloads.sourceforge.net/project/mod-qos/mod_qos-${MOD_QOS_VERSION}.tar.gz" \
    "https://sourceforge.net/projects/mod-qos/files/mod_qos-${MOD_QOS_VERSION}.tar.gz/download" \
    "https://sourceforge.net/projects/mod-qos/files/latest/download" \
    ; do \
    wget --tries=3 --waitretry=2 "$URL" -O "$MOD_QOS_ARCHIVE" && break || true; \
    done \
    ; test -s "$MOD_QOS_ARCHIVE" \
    ; tar -xzf "$MOD_QOS_ARCHIVE" -C /tmp \
    ; rm -f "$MOD_QOS_ARCHIVE" \
    ; MOD_QOS_SRC_DIR="$(find /tmp -maxdepth 1 -type d -name 'mod_qos-*' | head -n1)" \
    ; test -n "$MOD_QOS_SRC_DIR" \
    ; cd "$MOD_QOS_SRC_DIR/apache2" \
    ; apxs2 -i -a -c -lssl -lcrypto mod_qos.c \
    ; rm -rf "$MOD_QOS_SRC_DIR"

# ---------- Manager Runtime Stage ------------------
FROM ${RUNTIME_OS_IMAGE} AS scenescape-manager-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Scenescape Manager Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/docs/user-guide/index.md"

USER root
SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG CERTDOMAIN=scenescape.intel.com

ENV DEBIAN_FRONTEND=noninteractive
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/Scenescape
ARG FORCE_VAAPI

# Upgrade base OS packages and install runtime dependencies in one layer
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    apache2 \
    bzip2 \
    curl \
    ca-certificates \
    libegl1 \
    libgl1 \
    libapache2-mod-wsgi-py3 \
    libglib2.0-0 \
    libatomic1 \
    libusb-1.0-0 \
    libgomp1 \
    mosquitto-clients \
    netcat-openbsd \
    sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Runtime dependencies
COPY requirements-open3d-cpu.txt tools/install-open3d-cpu.sh /tmp/
COPY ./manager/requirements-runtime.txt /tmp/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --break-system-packages --ignore-installed --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements-runtime.txt \
    && /tmp/install-open3d-cpu.sh /tmp/requirements-open3d-cpu.txt pip3 \
    && rm -f /tmp/requirements-runtime.txt /tmp/requirements-open3d-cpu.txt /tmp/install-open3d-cpu.sh

COPY --from=scenescape-manager-builder /usr/lib/apache2/modules/mod_qos.so /usr/lib/apache2/modules/mod_qos.so
RUN echo "LoadModule qos_module /usr/lib/apache2/modules/mod_qos.so" > /etc/apache2/mods-available/qos.load

RUN : \
    ; a2dismod -f \
    auth_basic \
    authn_core \
    authn_file \
    authz_host \
    authz_user \
    autoindex \
    status \
    ; a2enmod \
    allowmethods \
    headers \
    proxy \
    proxy_http \
    proxy_wstunnel \
    ssl \
    qos \
    ; a2ensite default-ssl \
    ;

# mod_qos configuration
RUN cat > /etc/apache2/mods-available/qos.conf <<EOF
<IfModule qos_module>
   QS_ClientEntries 100000
   QS_SrvMaxConnPerIP 50
   MaxClients 256
   QS_SrvMaxConnClose 180
   QS_SrvMinDataRate 150 1200
</IfModule>
EOF

# Suppress warning about consecutive RUN instructions here
# hadolint ignore=DL3059
COPY ./manager/config/000-default.conf ./manager/config/default-ssl.conf /etc/apache2/sites-available/
COPY ./manager/config/apache2.conf /etc/apache2/
RUN : \
    ; sed -i "s/scenescape.intel.com/$CERTDOMAIN/g" /etc/apache2/sites-available/default-ssl.conf \
    ; chmod og-w /etc/apache2/sites-available/*.conf /etc/apache2/apache2.conf

RUN : \
    ; groupadd -g $GROUP_ID $WSUSER \
    ; useradd -r -u $USER_ID -g $GROUP_ID -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;
# End of TLS installation

# Copy application code
RUN mkdir -p $SCENESCAPE_HOME/manager
COPY ./manager/src/manager $SCENESCAPE_HOME/manager
COPY ./manager/src/manage.py $SCENESCAPE_HOME/manage.py
COPY ./version.txt $SCENESCAPE_HOME/manager/
COPY --from=scenescape-manager-builder /usr/local/lib/python3.14/site-packages/fast_geometry /usr/local/lib/python3.14/site-packages/fast_geometry
COPY --from=scenescape-manager-builder /usr/local/lib/python3.14/site-packages/scene_common /usr/local/lib/python3.14/site-packages/scene_common

# Install Scenescape
RUN : \
    ; eval WSHOME=~$WSUSER \
    ; chown -R "$WSUSER":"$WSUSER" "$WSHOME/Scenescape" \
    ; touch "$WSHOME/Scenescape/manager/settings_local.py" \
    ; chown "$WSUSER:$WSUSER" "$WSHOME/Scenescape/manager/settings_local.py" \
    ; pip3 install --break-system-packages --ignore-installed --no-cache-dir "$SCENESCAPE_HOME/manager/" \
    ;
RUN cp -R /usr/local/lib/python3.*/site-packages/django/contrib/admin/static/ $SCENESCAPE_HOME/

RUN chmod -R u=rwX,go=rX $SCENESCAPE_HOME/manager/static/assets/
RUN chmod -R u=rwX,go=rX $SCENESCAPE_HOME/manager/static/examples/
RUN chmod -R u=rwX,go=rX $SCENESCAPE_HOME/manager/static/bootstrap/

RUN OPENCV_SHA=$(openssl dgst -sha256 -binary "$SCENESCAPE_HOME/manager/static/assets/opencv.js" | openssl base64) && \
    sed -i "s|sha256-opencv|sha256-${OPENCV_SHA}|g" /etc/apache2/sites-available/000-default.conf

COPY ./manager/config/user_access_config.json $SCENESCAPE_HOME

COPY --chown=$WSUSER:$WSUSER ./manager/config/webserver-init \
    ./manager/config/scenescape-init \
    /usr/local/bin/

RUN chown -R $WSUSER:$WSUSER /home/scenescape/ \
    && chown -R $WSUSER:$WSUSER /etc/apache2/ \
    && mkdir -p /workspace /workspace/media /workspace/migrations \
    && chown -R $WSUSER:$WSUSER /workspace \
    && mkdir -p /var/log/apache2 \
    && chown -R $WSUSER:$WSUSER /var/log/apache2 \
    && mkdir -p /var/run/apache2 \
    && chown -R $WSUSER:$WSUSER /var/run/apache2
RUN sed -i "/^export APACHE_RUN_USER=/d" /etc/apache2/envvars && \
    sed -i "/^export APACHE_RUN_GROUP=/d" /etc/apache2/envvars && \
    echo "export APACHE_RUN_USER=$WSUSER" >> /etc/apache2/envvars && \
    echo "export APACHE_RUN_GROUP=$WSUSER" >> /etc/apache2/envvars
USER $WSUSER
ENTRYPOINT ["/usr/local/bin/scenescape-init"]

# ---------- Manager Test Stage ------------------
# This stage is meant to be used for test execution (not for final runtime)
FROM scenescape-manager-runtime AS scenescape-manager-test
ENV DEBIAN_FRONTEND=noninteractive
ARG TEST_USER
USER root
RUN : \
    ; getent group $TEST_USER >/dev/null 2>&1 || groupadd -g $TEST_USER tester \
    ; getent passwd $TEST_USER >/dev/null 2>&1 || useradd -r -u $TEST_USER -g $TEST_USER -m -s /bin/bash tester \
    ; usermod -a -G video,users $(id -nu $TEST_USER) \
    ;
RUN : \
    ; apt-get update \
    ; install -d -m 0755 /etc/apt/keyrings \
    ; apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    wget \
    libpci-dev \
    libnss3-tools \
    software-properties-common \
    unzip \
    xserver-xephyr \
    xvfb \
    ; wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- | tee /etc/apt/keyrings/packages.mozilla.org.asc > /dev/null \
    ; echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" | tee -a /etc/apt/sources.list.d/mozilla.list > /dev/null \
    ; echo -e ' \n\
    Package: * \n\
    Pin: origin packages.mozilla.org \n\
    Pin-Priority: 1000 \n\
    ' | tee /etc/apt/preferences.d/mozilla \
    ; apt-get update && apt-get install -y --no-install-recommends firefox-esr \
    ; rm -rf /var/lib/apt/lists/*
# Install Python test dependencies.
# pupil-apriltags has no cp314 wheels yet; build from source under C11 so GCC 15
# accepts the vendored AprilTag C sources.
COPY ./manager/test/requirements-test.txt /tmp
RUN CFLAGS="-std=gnu11 -Wno-error=incompatible-pointer-types" \
    pip3 install --break-system-packages --ignore-installed --upgrade --no-cache-dir \
    -r /tmp/requirements-test.txt

ADD ./manager/test/geckodriver.tar.gz /usr/local/bin/
RUN chmod a+rwx /usr/local/bin/geckodriver

COPY ./manager/test/firefox-profile.tar /home/scenescape/.mozilla/
RUN chmod -R a+rwx /home/scenescape/.mozilla

USER $TEST_USER
ENV PYTHONPATH=/home/scenescape/Scenescape/
ENTRYPOINT [""]
