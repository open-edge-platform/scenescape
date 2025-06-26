#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

FILE=$1
dpkg -s | egrep "Package|Version" > ${FILE}

PIP3PKGS="pyrealsense2 apriltag coverage django django-axes django-bootstrap-breadcrumbs django-crispy-forms django-debug-toolbar django-session-security djangorestframework ntplib onvif-zeep paho-mqtt psycopg2-binary selenium
"
pip3 show ${PIP3PKGS} >> ${FILE}

