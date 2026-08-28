#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Rebuild libgst3delements.so from a local dlstreamer checkout and bake it into
# a tagged DLSPS image for SceneScape lidar/radar demos.
#
# Usage (from scenescape repo root):
#   DLSTREAMER_SRC=../dlstreamer bash sample_data/dlstreamer-pipeline-server/build-g3d-image.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DLSTREAMER_SRC="${DLSTREAMER_SRC:-$(cd "${ROOT}/../dlstreamer" && pwd)}"
BASE_IMAGE="${DLS_BASE_IMAGE:-intel/dlstreamer-pipeline-server:2026.2.0-ubuntu24-rc2}"
OUT_IMAGE="${DLS_G3D_IMAGE:-intel/dlstreamer-pipeline-server:2026.2.0-ubuntu24-rc2-g3d}"
PLUGIN_OUT="${DLSTREAMER_SRC}/build-3delements-out"
DOCKERFILE="${ROOT}/sample_data/dlstreamer-pipeline-server/Dockerfile.g3dinference"

if [[ ! -f "${DLSTREAMER_SRC}/scripts/rebuild_3delements_plugin.sh" ]]; then
  echo "Missing ${DLSTREAMER_SRC}/scripts/rebuild_3delements_plugin.sh" >&2
  echo "Set DLSTREAMER_SRC to a checkout with feature/g3dinference-multi-model." >&2
  exit 1
fi

mkdir -p "${PLUGIN_OUT}"
echo "[build-g3d-image] Rebuilding libgst3delements.so from ${DLSTREAMER_SRC}"
docker run --rm -u root --entrypoint bash \
  -v "${DLSTREAMER_SRC}:/src/dlstreamer" \
  -v "${PLUGIN_OUT}:/out" \
  "${BASE_IMAGE}" \
  /src/dlstreamer/scripts/rebuild_3delements_plugin.sh /out

cp -f "${PLUGIN_OUT}/libgst3delements.so" \
  "${ROOT}/sample_data/dlstreamer-pipeline-server/libgst3delements.so"

echo "[build-g3d-image] Building ${OUT_IMAGE}"
docker build \
  -f "${DOCKERFILE}" \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  -t "${OUT_IMAGE}" \
  "${ROOT}/sample_data/dlstreamer-pipeline-server"

rm -f "${ROOT}/sample_data/dlstreamer-pipeline-server/libgst3delements.so"
echo "[build-g3d-image] Done → ${OUT_IMAGE}"
