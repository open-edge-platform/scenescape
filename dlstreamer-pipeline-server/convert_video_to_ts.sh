#!/bin/sh

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# script to convert mp4 files in sample-data directory
# to ts files so that gstreamer pipeline can keep running the files
# in infinite loop without having to deallocate buffers

docker pull intel/intel-optimized-ffmpeg:avx3

DIRNAME=${PWD}
SAMPLE_DATA_DIRECTORY=${DIRNAME}/sample_data
FFMPEG_DIR="/app/data"
FFMPEG_IMAGE="intel/intel-optimized-ffmpeg:avx3"
EXTENSION=${1:-mp4}
PATTERN="*.${EXTENSION}"

DOCKER_RUN_CMD_PREFIX="docker run --rm -v ${SAMPLE_DATA_DIRECTORY}:${FFMPEG_DIR} \
            --entrypoint /bin/sh ${FFMPEG_IMAGE}"

for mfile in "$SAMPLE_DATA_DIRECTORY"/$PATTERN; do
    basefile=$(basename -s .$EXTENSION $mfile)
    tsfile=${SAMPLE_DATA_DIRECTORY}/${basefile}.ts
    echo $tsfile
    if [ -f $tsfile ]; then
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
        ffmpegcmd="/opt/build/bin/ffmpeg -i ${FFMPEG_DIR}/${basefile}.${EXTENSION} -c:v libx264 -preset medium -crf 33 -x264opts keyint=12:min-keyint=12:scenecut=0 -forced-idr 1 -fflags +genpts -pix_fmt yuv420p -c:a copy ${FFMPEG_DIR}/${basefile}.ts"
        cmd="$DOCKER_RUN_CMD_PREFIX -c '$ffmpegcmd'"
        eval $cmd
    fi
done

