#!/usr/bin/env bash
set -euo pipefail

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Converts sample mp4 videos (per-scene under demo_scenes/*/video, plus the
# shared sample_data/videos) to ts so the gstreamer pipeline can loop them
# infinitely without deallocating buffers.

docker pull intel/intel-optimized-ffmpeg:avx3

DIRNAME=${PWD}
SAMPLE_DATA_DIR=${DIRNAME}/sample_data
FFMPEG_DIR="/app/data"
FFMPEG_IMAGE="intel/intel-optimized-ffmpeg:avx3"
EXTENSION=${1:-mp4}

DOCKER_RUN_CMD_PREFIX="docker run --rm -v ${SAMPLE_DATA_DIR}:${FFMPEG_DIR} \
            --entrypoint /bin/sh ${FFMPEG_IMAGE}"

for mfile in "$SAMPLE_DATA_DIR"/demo_scenes/*/video/*."${EXTENSION}" "$SAMPLE_DATA_DIR"/videos/*."${EXTENSION}"; do
  [ -f "$mfile" ] || continue
  # relative dir under sample_data/, so the ts file lands next to its source mp4
  reldir=$(dirname "${mfile#"$SAMPLE_DATA_DIR"/}")
  basefile=$(basename -s ".$EXTENSION" "$mfile")
  tsfile="${SAMPLE_DATA_DIR}/${reldir}/${basefile}.ts"
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
    ffmpegcmd="/opt/build/bin/ffmpeg -i ${FFMPEG_DIR}/${reldir}/${basefile}.${EXTENSION} -c:v libx264 -preset medium -crf 33 -x264opts keyint=12:min-keyint=12:scenecut=0 -forced-idr 1 -fflags +genpts -pix_fmt yuv420p -c:a copy ${FFMPEG_DIR}/${reldir}/${basefile}.ts"
    cmd="$DOCKER_RUN_CMD_PREFIX -c '$ffmpegcmd'"
    eval "$cmd"
  fi
done

