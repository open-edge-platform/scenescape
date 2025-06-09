#!/bin/bash

# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

TESTBASE="tests/perf_tests/"

COMPOSEDIR="${TESTBASE}/compose"
YMLFILE="docker-compose-inference_threading.yml"

TEST_NAME="NEX-T10421"

MODELS=${1:-${MODELS}}
INPUTS=${2:-${INPUTS}}
VIDEO_FRAMES=${3:-2000}
TARGET_FPS=${4:-5}

#Run the test...

echo Executing: ${TEST_NAME}
#Params that wont change

export MODELS=${MODELS}
export VIDEO_FRAMES=${VIDEO_FRAMES}
export TARGET_FPS=${TARGET_FPS}
export INPUTS=${INPUTS}

echo "Starting test for ${TEST_INF_THREADS} inference threads..."
docker compose -f ${COMPOSEDIR}/${YMLFILE} --project-directory ${PWD} run test
RESULT=$?


if [[ $RESULT -eq 0 ]]
then
    echo "${TEST_NAME}: PASS"
else
    echo "${TEST_NAME}: FAIL"
fi

exit $RESULT
