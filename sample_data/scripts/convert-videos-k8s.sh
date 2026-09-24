#!/bin/sh

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -eu
echo "Converting .mp4 files to .ts..."
if [ -f /workspace/sample-data-storage/sample_data/.done ]; then
  echo ".done file exists in /workspace/sample-data-storage/sample_data/"
else
  for mp4_file in /workspace/sample-data-storage/sample_data/*.mp4; do
      ts_file="${mp4_file%.mp4}.ts"
      echo "Converting $mp4_file to $ts_file..."
      /ffmpegwrapper.sh -i "$mp4_file" -c copy "$ts_file"
  done
fi
