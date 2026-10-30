# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM nodered/node-red@sha256:e085d4a06591fd0aca2ea2a91364d27f1a0e31e885675f77935e10f95412a963

# Pre-install required nodes
COPY package.json package-lock.json /data/
RUN cd /data && npm ci
COPY --chown=node-red:node-red flows/flows.json /data/flows.json

USER node-red
