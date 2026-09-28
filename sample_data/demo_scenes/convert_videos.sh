#!/usr/bin/env bash
set -euo pipefail

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Converts sample mp4 videos (per-scene under demo_scenes/*/video, plus
# tools/pipeline_runner/video) to ts so the gstreamer pipeline can loop them
# infinitely without deallocating buffers.

docker pull intel/intel-optimized-ffmpeg:avx3

DIRNAME=${PWD}
FFMPEG_DIR="/app/data"
FFMPEG_IMAGE="intel/intel-optimized-ffmpeg:avx3"
EXTENSION=${1:-mp4}

for mfile in "$DIRNAME"/sample_data/demo_scenes/*/video/*."${EXTENSION}" "$DIRNAME"/tools/pipeline_runner/video/*."${EXTENSION}"; do
  [ -f "$mfile" ] || continue
  # relative dir under the repo root, so the ts file lands next to its source mp4
  reldir=$(dirname "${mfile#"$DIRNAME"/}")
  basefile=$(basename -s ".$EXTENSION" "$mfile")
  tsfile="${DIRNAME}/${reldir}/${basefile}.ts"
  echo "$tsfile"
  if [ -f "$tsfile" ]; then
    echo "skipping $basefile as $tsfile is available already"
  else
    # Re-encode with regular IDR keyframes to prevent loop-boundary artifacts:
    # -c:v libx264            : H.264 video codec (streaming-friendly)
    # -preset medium          : encoding speed/quality balance (medium CPU cost)
    # -crf 33                 : quality level (33 = moderate compression)
    # -x264opts keyint=12     : force keyframe every 12 frames (~0.5s at 24fps)
    # -x264opts min-keyint=12 : ensure consistent keyframe spacing
    # -x264opts scenecut=0    : disable auto-keyframes on scene transitions
    # -forced-idr 1           : make all keyframes IDRs (full decoder reset)
    # -fflags +genpts         : regenerate clean presentation timestamps
    # -pix_fmt yuv420p        : standard H.264 pixel format (4:2:0 chroma)
    # -c:a copy               : audio stream-copied (no re-encode)
    docker run --rm \
      -v "${DIRNAME}:${FFMPEG_DIR}" \
      --entrypoint /opt/build/bin/ffmpeg \
      "$FFMPEG_IMAGE" \
      -i "${FFMPEG_DIR}/${reldir}/${basefile}.${EXTENSION}" \
      -c:v libx264 \
      -preset medium \
      -crf 33 \
      -x264opts keyint=12:min-keyint=12:scenecut=0 \
      -forced-idr 1 \
      -fflags +genpts \
      -pix_fmt yuv420p \
      -c:a copy \
      "${FFMPEG_DIR}/${reldir}/${basefile}.ts"
  fi
done

