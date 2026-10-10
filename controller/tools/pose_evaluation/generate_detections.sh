#!/bin/bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Generate detection NDJSON files for pose adjustment evaluation.
# Runs DL Streamer inference with yolo11m-pose + DeepSORT tracking.
#
# Prerequisites:
#   - Docker installed
#   - intel/dlstreamer:latest image pulled
#   - Models downloaded to my_models/models/public/
#   - Sample videos in sample_data/
#
# Usage:
#   ./controller/tools/pose_evaluation/generate_detections.sh

set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")/../../.." && pwd)"
CONTAINER_IMAGE="intel/dlstreamer:latest"
POSE_MODEL="/workspace/my_models/models/public/yolo11m-pose/FP32/yolo11m-pose.xml"
REID_MODEL="/workspace/my_models/models/public/mars-small128/mars_small128_fp32.xml"
TRACKER_CFG="max_age=60,max_cosine_distance=0.2"

OCCLUDED_VIDEO="/workspace/sample_data/qcam2_occlusion_improved_less_occlusion_short.mp4"
BASELINE_VIDEO="/workspace/sample_data/qcam2_short.mp4"

echo "=== Generating detection data ==="
echo "Workspace: ${WORKSPACE}"
echo ""

run_pipeline() {
  local input_video="$1"
  local output_json="$2"
  local output_video="$3"
  local description="$4"

  echo "--- ${description} ---"
  echo "  Input:  ${input_video}"
  echo "  Output: ${output_json}"

  docker run --rm -v "${WORKSPACE}:/workspace" "${CONTAINER_IMAGE}" \
    gst-launch-1.0 \
      filesrc location="${input_video}" ! decodebin3 ! \
      gvadetect model="${POSE_MODEL}" device=CPU ! queue ! \
      gvainference model="${REID_MODEL}" device=CPU inference-region=roi-list ! \
      gvatrack tracking-type=deep-sort deepsort-trck-cfg="${TRACKER_CFG}" ! queue ! \
      gvametaconvert ! \
      tee name=t ! queue ! \
        gvametapublish method=file file-path="/workspace/${output_json}" file-format=json-lines ! \
        fakesink \
      t. ! queue ! \
        gvawatermark ! gvafpscounter ! \
        openh264enc bitrate=2000000 ! h264parse ! mp4mux ! \
        filesink location="/workspace/${output_video}"

  echo "  Done: $(wc -l < "${WORKSPACE}/${output_json}") frames"
  echo ""
}

run_pipeline "${BASELINE_VIDEO}" \
  "no_occlusion_detections.json" \
  "no_occlusion_output.mp4" \
  "Baseline (no occlusion)"

run_pipeline "${OCCLUDED_VIDEO}" \
  "detections.json" \
  "occluded_output.mp4" \
  "Occluded video"

echo "=== Detection generation complete ==="
echo ""
echo "Next steps:"
echo "  1. Apply pose adjustment:"
echo "     PYTHONPATH=controller/src:scene_common/src python3 \\"
echo "       controller/tools/pose_evaluation/pose_adjustment_debug.py \\"
echo "       --input detections.json --output adjusted.json"
echo ""
echo "  2. Visualize:"
echo "     python3 controller/tools/pose_evaluation/visualize_pose_adjustment.py \\"
echo "       --video sample_data/qcam2_occlusion_improved_less_occlusion_short.mp4 \\"
echo "       --original detections.json --adjusted adjusted.json"
echo ""
echo "  3. Compare metrics:"
echo "     python3 controller/tools/pose_evaluation/compare_pose_adjustment.py \\"
echo "       --occluded detections.json --baseline no_occlusion_detections.json \\"
echo "       --adjusted adjusted.json"
