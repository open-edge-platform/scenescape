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

FROM scenescape-common-base AS manager-builder

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
    && rm -rf /var/lib/apt/lists/*

# ---------- Manager Runtime Stage ------------------
FROM ubuntu:22.04 AS manager-runtime

USER root
SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]
ARG USER_ID
ARG CERTDOMAIN=scenescape.intel.com

ENV DEBIAN_FRONTEND=noninteractive
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape
ARG FORCE_VAAPI

RUN : \
&& apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt jammy-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        apache2 \
        bindfs \
        bzip2 \
        libegl1 \
        libgl1 \
        libapache2-mod-wsgi-py3 \
        libapache2-mod-qos \
        libglib2.0-0 \
        libgomp1 \
        mosquitto-clients \
        netcat \
        postgresql-15 \
        python-is-python3 \
        python3-pip \
        sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Runtime dependencies
COPY ./manager/requirements-runtime.txt /tmp
RUN pip3 install --upgrade --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /tmp/requirements-runtime.txt

RUN : \
    ; PSQLVER=$(ls /etc/postgresql) \
    ; echo "host all  all    0.0.0.0/0  md5" >> "/etc/postgresql/${PSQLVER}/main/pg_hba.conf" \
    ; echo "listen_addresses='*'" >> "/etc/postgresql/${PSQLVER}/main/postgresql.conf" \
    ;

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
        proxy_wstunnel \
        ssl \
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
    ; useradd -r -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;
# End of TLS installation

RUN mkdir -p $SCENESCAPE_HOME/manager
COPY ./manager/src/django/* \
     ./manager/src/setup.py \
     ./version.txt $SCENESCAPE_HOME/manager/
COPY ./manager/src/management/ $SCENESCAPE_HOME/manager/management
COPY ./manager/src/templates/ $SCENESCAPE_HOME/manager/templates
COPY ./manager/src/static/ $SCENESCAPE_HOME/manager/static
COPY ./manager/src/templatetags/ $SCENESCAPE_HOME/manager/templatetags
COPY ./manager/src/django/manage.py $SCENESCAPE_HOME
COPY --from=manager-builder /usr/local/lib/python3.10/dist-packages/fast_geometry /usr/local/lib/python3.10/dist-packages/fast_geometry
COPY --from=manager-builder /usr/local/lib/python3.10/dist-packages/scene_common /usr/local/lib/python3.10/dist-packages/scene_common

# Install SceneScape
RUN : \
    ; eval WSHOME=~$WSUSER \
    ; chown -R "$WSUSER" "$WSHOME/SceneScape" \
    ; touch "$WSHOME/SceneScape/manager/settings_local.py" \
    ; chown "$WSUSER.$WSUSER" "$WSHOME/SceneScape/manager/settings_local.py" \
    ; pip3 install --no-cache-dir "$SCENESCAPE_HOME/manager/" \
    ;
RUN cp -R /usr/local/lib/python3.*/dist-packages/django/contrib/admin/static/ $SCENESCAPE_HOME/

RUN chmod -R u=rwX,go=rX $SCENESCAPE_HOME/manager/static/assets/
RUN chmod -R u=rwX,go=rX $SCENESCAPE_HOME/manager/static/examples/
RUN chmod -R u=rwX,go=rX $SCENESCAPE_HOME/manager/static/bootstrap/

RUN OPENCV_SHA=$(openssl dgst -sha256 -binary "$SCENESCAPE_HOME/manager/static/assets/opencv.js" | openssl base64) && \
    sed -i "s|sha256-opencv|sha256-${OPENCV_SHA}|g" /etc/apache2/sites-available/000-default.conf

COPY ./manager/config/user_access_config.json $SCENESCAPE_HOME

COPY ./manager/config/webserver-init \
     ./manager/config/database-init \
     ./manager/config/scenescape-init \
     /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/scenescape-init"]

# ---------- Manager Test Stage ------------------
# This stage is meant to be used for test execution (not for final runtime)
FROM manager-runtime AS manager-test

USER root
ENV DEBIAN_FRONTEND=noninteractive

RUN : \
    ; apt-get update \
    ; install -d -m 0755 /etc/apt/keyrings \
    ; apt-get install -y --no-install-recommends \
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
    ; apt-get update && apt-get install -y --no-install-recommends firefox \
    ; rm -rf /var/lib/apt/lists/*

# Install Python test dependencies
COPY ./manager/test/requirements-test.txt /tmp
RUN pip3 install --upgrade --no-cache-dir -r /tmp/requirements-test.txt

ADD ./manager/test/geckodriver.tar.gz /usr/local/bin/

COPY ./manager/test/firefox-profile.tar /home/scenescape/.mozilla/

RUN : \
    ; eval WSHOME=~$WSUSER \
    ; chown -R "$WSUSER.$WSUSER" "$WSHOME/.mozilla" \
    ;
