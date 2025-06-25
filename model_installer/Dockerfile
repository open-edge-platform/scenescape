# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

FROM python:3.10-slim

USER root

RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

COPY ./model_installer/requirements-runtime.txt /tmp
RUN : \
    ; pip install -r /tmp/requirements-runtime.txt \
    ; rm -rf /tmp/requirements-runtime.txt \
    ;
