# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM ubuntu:24.04

USER root

RUN apt-get update && apt-get install -y --no-install-recommends wget python3 python3-pip python3-venv git curl && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd --create-home --shell /bin/bash model_installer_user

SHELL ["/bin/bash", "-e", "-o", "pipefail", "-c"]

COPY ./model_installer/requirements-runtime.txt /tmp
COPY ./model_installer/src/install_dependencies.sh /tmp/

# Change ownership so non-root user can access the files
RUN chown model_installer_user:model_installer_user /tmp/requirements-runtime.txt /tmp/install_dependencies.sh \
    && chmod +x /tmp/install_dependencies.sh

USER model_installer_user

RUN : \
    ; pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements-runtime.txt \
    ; rm -rf /tmp/requirements-runtime.txt \
    ;

# Install Python dependencies for model processing
RUN /tmp/install_dependencies.sh && rm /tmp/install_dependencies.sh

HEALTHCHECK CMD true
