#!/bin/bash

# Copyright (C) 2021-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

TEST_NAME="NEX-T10412"
echo "Executing: ${TEST_NAME}"

TESTBASE="tests/perf_tests/"

COMPOSEDIR="${TESTBASE}/compose"
YMLFILE="docker-compose-inference_performance.yml"

MODELS=${1:-${MODELS}}
INPUTS=${2:-${INPUTS}}
VIDEO_FRAMES=${3:-${VIDEO_FRAMES}}
TARGET_FPS=${4:-${TARGET_FPS}}
OVCORES=${5:-${OVCORES}}
MODEL_CONFIG=${6:-${MODEL_CONFIG}}

#Run the test...

#Single stream
MODELS=${MODELS} VIDEO_FRAMES=${VIDEO_FRAMES} TARGET_FPS=${TARGET_FPS} INPUTS=${INPUTS} OVCORES=${OVCORES} docker compose -f ${COMPOSEDIR}/${YMLFILE} --project-directory ${PWD} run test
RESULT=$?

if [[ $RESULT -eq 0 ]]
then
    echo "${TEST_NAME}: PASS"
else
    echo "${TEST_NAME}: FAIL"
fi

exit $RESULT
