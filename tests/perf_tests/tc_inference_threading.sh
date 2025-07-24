#!/bin/bash

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
