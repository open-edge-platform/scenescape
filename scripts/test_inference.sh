#!/bin/bash

REQUIRED_FPS=${REQUIRED_FPS:-20}
if ! tests/perf_tests/tc_inference_performance.sh retail \
     "sample_data/apriltag-cam1.mp4 sample_data/apriltag-cam2.mp4" 500 \
     $REQUIRED_FPS ; then
    echo "The performance of this computer is insufficient"
    echo "At least ${REQUIRED_FPS}FPS is required for inferencing"
    exit 1
fi