#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Renders ptz-config.json / ptz-config-gpu.json from their .template files,
# substituting RTSP camera credentials from the environment. Keeps real
# credentials out of git: only the rendered files (gitignored) contain them.
#
# Required env vars: RTSP_CAM1_USER, RTSP_CAM1_PASS, RTSP_CAM2_USER, RTSP_CAM2_PASS,
#                     RTSP_CAM3_USER, RTSP_CAM3_PASS
# Note: if a username/password contains ':', '@', or '/', percent-encode it
# (e.g. "p@ss" -> "p%40ss") since those characters are RTSP URL delimiters.
# Note: cam3 (TP-Link VIGI, 192.168.0.91) uses the /stream1 path (its main
# stream); switch to /stream2 in the .template files if you need the substream.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for var in RTSP_CAM1_USER RTSP_CAM1_PASS RTSP_CAM2_USER RTSP_CAM2_PASS RTSP_CAM3_USER RTSP_CAM3_PASS; do
  [[ -n "${!var:-}" ]] || { echo "ERROR: $var must be set" >&2; exit 1; }
done

for name in ptz-config ptz-config-gpu; do
  envsubst '${RTSP_CAM1_USER} ${RTSP_CAM1_PASS} ${RTSP_CAM2_USER} ${RTSP_CAM2_PASS} ${RTSP_CAM3_USER} ${RTSP_CAM3_PASS}' \
    < "$SCRIPT_DIR/$name.json.template" > "$SCRIPT_DIR/$name.json"
done

echo "Rendered ptz-config.json and ptz-config-gpu.json with camera credentials."
