# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---------------------------
# Stage 1: Build RESTler and Python deps
# ---------------------------
# RESTler publishes net8.0 applications; keep the SDK and runtime on .NET 8.
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

# Fix upstream coverage lookup for sequences with multiple prerequisites.
# Preserve engine rendering-ID separators instead of hiding missing-prefix errors.
# Accept an upstream-fixed source, but fail if the expected code has changed.
RUN python3 - <<'PY'
from pathlib import Path

path = Path("src/driver/SpecCoverage.fs")
source = path.read_text()
replacements = (
    ('Seq.take idx |> String.concat ""', 'Seq.take idx |> String.concat "_"'),
    ('sprintf "%s%s" firstRendering prefixRendering',
     'if String.IsNullOrEmpty prefixRendering then firstRendering '
     'else sprintf "%s__%s" firstRendering prefixRendering'),
)
for old, new in replacements:
    if source.count(old) == 1:
        source = source.replace(old, new, 1)
    elif source.count(old) != 0 or source.count(new) != 1:
        raise RuntimeError("RESTler coverage source changed; review rendering-ID compatibility fix")
path.write_text(source)
PY

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
