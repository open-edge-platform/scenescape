# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM nodered/node-red@sha256:b5adb6c9dd29ab80c852d82bc87daed84e729dcff9b00ca1bf958e6de470f2c1

# Pre-install required nodes
COPY package.json package-lock.json /data/
RUN cd /data && npm ci
COPY --chown=node-red:node-red flows/flows.json /data/flows.json

USER node-red
