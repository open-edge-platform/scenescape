# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM nodered/node-red@sha256:3622786c15b6f57f61bf1d0ece59d06a18b742c5c8955f588d189b6bee8dc97d

# Pre-install required nodes
COPY package.json package-lock.json /data/
RUN cd /data && npm ci
COPY --chown=node-red:node-red flows/flows.json /data/flows.json

USER node-red
