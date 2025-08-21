#!/bin/bash
# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

BROKER="broker.scenescape.intel.com"
PORT=1883
CAMERA1_TOPIC="scenescape/data/camera/camera1"
CAMERA2_TOPIC="scenescape/data/camera/camera2"
CAFILE="/run/secrets/certs/scenescape-ca.pem"
NUM_MESSAGES=1000

if [ ! -f "$CAFILE" ]; then
  echo "Error: CA file not found at $CAFILE" >&2
  exit 1
fi

collect_avg_fps() {
  local topic=$1
  echo "Collecting $NUM_MESSAGES messages from $topic..." >&2
  mosquitto_sub -h "$BROKER" -p "$PORT" -t "$topic" --cafile "$CAFILE" \
    | awk -v limit="$NUM_MESSAGES" '
      BEGIN {
        count = 0;
        sum = 0;
      }
      {
        pos = index($0, "\"rate\":")
        if (pos > 0) {
          rest = substr($0, pos + 7)
          gsub(/^[ \t]+/, "", rest)
          split(rest, parts, ",")
          rate = parts[1] + 0
          sum += rate
          count++
        }
        if (count >= limit) {
          avg = sum / count
          print avg
          exit
        }
      }
    '
}

avg1=$(collect_avg_fps "$CAMERA1_TOPIC")
avg2=$(collect_avg_fps "$CAMERA2_TOPIC")

echo "camera1_avg_fps=$avg1"
echo "camera2_avg_fps=$avg2"
