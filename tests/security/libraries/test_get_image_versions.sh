#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FILE=$1
dpkg -s | egrep "Package|Version" > ${FILE}

PIP3PKGS="apriltag coverage django django-axes django-bootstrap-breadcrumbs django-crispy-forms django-debug-toolbar django-session-security djangorestframework ntplib onvif-zeep paho-mqtt psycopg2-binary selenium
"
pip3 show ${PIP3PKGS} >> ${FILE}

