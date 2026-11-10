# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM nodered/node-red@sha256:2ccd38b4066648bd5e17430c50a2f8102c566a82fd4f2fc5c342e61664d6896f

# Pre-install required nodes
COPY package.json package-lock.json /data/
RUN cd /data && npm ci
COPY --chown=node-red:node-red flows/flows.json /data/flows.json

USER node-red
