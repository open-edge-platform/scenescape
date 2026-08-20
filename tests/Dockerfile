# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM docker.io/intel/dlstreamer-pipeline-server:${VERSION:-latest}

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages --no-deps pupil-apriltags

# Restore the pipeline server user from the base image (uid/gid 1999, in the video group).
USER intelmicroserviceuser
