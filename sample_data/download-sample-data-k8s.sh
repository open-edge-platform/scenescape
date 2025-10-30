#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
apt update && apt install -y wget
if [ -f /workspace/sample-data-storage/sample_data/.done ]; then
    echo ".done file exists in /workspace/sample-data-storage/sample_data/"
else
    echo ".done file does NOT exist in /workspace/sample-data-storage/sample_data/"
    echo "Downloading videos from GitHub..."
    mkdir -p /workspace/sample-data-storage/sample_data/
    SAMPLE_DATA_URL="{{ .Values.sampleData.source }}/{{ .Values.sampleData.sourceVersion }}/{{ .Values.sampleData.sourceDir }}"
    FILES="{{ join " " .Values.sampleData.files }}"
    for file in $FILES; do
        echo "Downloading $file..."
        wget -O "/workspace/sample-data-storage/sample_data/$file" "$SAMPLE_DATA_URL/$file"
    done
    echo "Sample data downloaded successfully"
fi
