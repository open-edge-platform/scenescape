# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---------------------------
# Stage 1: Build RESTler and Python deps
# ---------------------------
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder

# Install Python and pip (using the .NET SDK image's underlying Debian)
RUN apt-get update && \
apt-get install -y --no-install-recommends \
    python3 \
    curl \
    jq && \
rm -rf /var/lib/apt/lists/*

# Copy app and RESTler code
COPY src ./src
COPY restler ./restler
COPY build-restler.py .

# Build RESTler output into /build
RUN python3 build-restler.py --dest_dir /build

# Byte-compile Python files
RUN python3 -m compileall -b /build/engine

# ---------------------------
# Stage 2: Runtime
# ---------------------------
FROM mcr.microsoft.com/dotnet/runtime:8.0 AS runtime

# Install CA certs and Python (since RESTler needs Python)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    curl \
    jq && \
rm -rf /var/lib/apt/lists/*

COPY scenescape-ca.pem /usr/local/share/ca-certificates/scenescape-ca.crt

RUN update-ca-certificates

# Copy only the compiled RESTler build output
COPY --from=builder /build /RESTler
