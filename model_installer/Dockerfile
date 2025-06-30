# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

FROM debian:12-slim

USER root

RUN apt-get update && apt-get install -y --no-install-recommends wget python3 python3-pip && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

COPY ./model_installer/requirements-runtime.txt /tmp
RUN : \
    ; pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements-runtime.txt \
    ; rm -rf /tmp/requirements-runtime.txt \
    ;
