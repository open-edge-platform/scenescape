#!/bin/bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

rm -f /tmp/healthy

if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then
    echo "Checking NetVLAD model..."
    python3 /usr/local/bin/download_models.py
fi

touch /tmp/healthy
exec "$@"
