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
ARG FORCE_VAAPI

# SceneScape requirements
COPY requirements-dockerfile.txt /tmp
RUN : \
    ; apt-get update \
    ; apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        bzip2 \
        curl \
        g++ \
        libboost-python-dev \
        libegl1 \
        libeigen3-dev \
        libgl1 \
        libglib2.0 \
        libgtest-dev \
        make \
        mosquitto-clients \
        netcat \
        patch \
        pybind11-dev \
        python-is-python3 \
        python3-dev \
        python3-pip \
        python3-scipy \
        sudo \
    ; apt-get purge -y python3-numpy \
    ; rm -rf /var/lib/apt/lists/* \
    ; pip3 install --upgrade --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /tmp/requirements-dockerfile.txt \
    ; rm -rf /tmp/requirements-dockerfile.txt \
    ;

ENV WSUSER=scenescape

RUN : \
    ; useradd -r -m -s /bin/bash $WSUSER \
    ; usermod -a -G video,users $WSUSER \
    ; eval WSHOME=~$WSUSER \
    ; chmod a+rX "${WSHOME}" \
    ;

# PostgreSQL database installation
RUN : \
    ; apt-get update \
    ; apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        bindfs \
        postgresql \
    ; rm -rf /var/lib/apt/lists/* \
    ; PSQLVER=$(ls /etc/postgresql) \
    ; echo "host all  all    0.0.0.0/0  md5" >> "/etc/postgresql/${PSQLVER}/main/pg_hba.conf" \
    ; echo "listen_addresses='*'" >> "/etc/postgresql/${PSQLVER}/main/postgresql.conf" \
    ;

RUN : \
    ; apt-get update \
    ; apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        apache2 \
        libapache2-mod-wsgi-py3 \
        libapache2-mod-qos \
    ; rm -rf /var/lib/apt/lists/* \
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

ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

# Suppress warning about consecutive RUN instructions here
# hadolint ignore=DL3059
RUN cp -R /usr/local/lib/python3.*/dist-packages/django/contrib/admin/static/ $SCENESCAPE_HOME/
COPY 000-default.conf default-ssl.conf /etc/apache2/sites-available/
COPY apache2.conf /etc/apache2/
RUN : \
    ; sed -i "s/scenescape.intel.com/$CERTDOMAIN/g" /etc/apache2/sites-available/default-ssl.conf \
    ; chmod og-w /etc/apache2/sites-available/*.conf /etc/apache2/apache2.conf

# End of TLS installation

# Be sure to update this line if the user or home directory changes
COPY --chown=${USER_ID} editor/js $SCENESCAPE_HOME/sscape/static/js/editor
COPY --chown=${USER_ID} editor/images $SCENESCAPE_HOME/sscape/static/images
COPY --chown=${USER_ID} editor/css $SCENESCAPE_HOME/sscape/static/css
COPY --chown=${USER_ID} jslibs/assets $SCENESCAPE_HOME/sscape/static/assets
COPY --chown=${USER_ID} jslibs/examples $SCENESCAPE_HOME/sscape/static/examples
COPY --chown=${USER_ID} jslibs/bootstrap $SCENESCAPE_HOME/sscape/static/bootstrap
RUN : \
    ; chmod -R u=rwX,go=rX $SCENESCAPE_HOME/sscape/static/js/editor/ \
    $SCENESCAPE_HOME/sscape/static/examples/ \
    ; OPENCV_SHA=$(openssl dgst -sha256 -binary $SCENESCAPE_HOME/sscape/static/assets/opencv.js | openssl base64) \
    ; sed -i "s|sha256-opencv|sha256-$OPENCV_SHA|g" /etc/apache2/sites-available/000-default.conf \
    ;

ADD SceneScape.tar $SCENESCAPE_HOME/
RUN : \
    ; eval WSHOME=~$WSUSER \
    ; chown -R "$WSUSER" "$WSHOME/SceneScape" \
    ; touch "$WSHOME/SceneScape/sscape/settings_local.py" \
    ; chown "$WSUSER.$WSUSER" "$WSHOME/SceneScape/sscape/settings_local.py" \
    ; pip3 install --no-cache-dir "$SCENESCAPE_HOME/sscape/" \
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

RUN : \
    ; apt-get purge -y --auto-remove make g++ \
    ; apt-get clean \
    ;

COPY scenescape-init \
     database-init \
     webserver-init \
     /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/scenescape-init"]
