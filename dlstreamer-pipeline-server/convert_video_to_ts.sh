#!/bin/sh

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

# script to convert mp4 files in sample-data directory
# to ts files so that gstreamer pipeline can keep running the files
# in infinite loop without having to deallocate buffers

docker pull intel/intel-optimized-ffmpeg:latest

DIRNAME=${PWD}
SAMPLE_DATA_DIRECTORY=${DIRNAME}/sample_data
FFMPEG_DIR="/app/data"
FFMPEG_IMAGE="intel/intel-optimized-ffmpeg:latest"
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
        ffmpegcmd="/opt/build/bin/ffmpeg -i ${FFMPEG_DIR}/${basefile}.${EXTENSION} -c copy ${FFMPEG_DIR}/${basefile}.ts"
        cmd="$DOCKER_RUN_CMD_PREFIX -c '$ffmpegcmd'"
        eval $cmd
    fi
done

