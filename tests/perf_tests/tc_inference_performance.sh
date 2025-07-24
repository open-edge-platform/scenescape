#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
