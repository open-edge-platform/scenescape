#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Gracefully stops every pipeline instance running in the ptz-video container
# via its REST API before the container itself is stopped/restarted.
#
# Why: some RTSP cameras (e.g. TP-Link VIGI) cap the number of concurrent
# RTSP sessions they'll accept. A plain `docker compose restart/down/stop`
# sends SIGTERM/SIGKILL to the container; if that doesn't give GStreamer time
# to tear the RTSP session down cleanly, the camera can be left thinking the
# old session is still active ("429 Stream Up To Limit") until its own
# session timeout expires - even though nothing is actually connected
# anymore. Calling DELETE on each running/queued instance first makes the
# pipeline-server tear down its rtspsrc (sending RTSP TEARDOWN) immediately,
# freeing the camera's connection slot right away.
#
# Usage: run this before `docker compose restart ptz-video` (or down/stop).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

ids=$(docker compose exec -T ptz-video curl -s http://localhost:8080/pipelines/status \
  | python3 -c "import json,sys; print('\n'.join(p['id'] for p in json.load(sys.stdin)))" 2>/dev/null || true)

if [[ -z "$ids" ]]; then
  echo "No running pipeline instances found (container not up, or nothing running)."
  exit 0
fi

while IFS= read -r id; do
  [[ -z "$id" ]] && continue
  echo "Stopping pipeline instance $id..."
  docker compose exec -T ptz-video curl -s -X DELETE "http://localhost:8080/pipelines/$id" >/dev/null
done <<< "$ids"

echo "All pipeline instances stopped."
