#!/bin/bash

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

MODELS_DEFAULT=retail
INPUTS_DEFAULT="sample_data/apriltag-cam1.mp4 sample_data/apriltag-cam2.mp4"
VIDEO_FRAMES_DEFAULT=1000
TARGET_FPS_DEFAULT=15.0

CVCORES_DEFAULT=1
OVCORES_DEFAULT=4

MODELS=${MODELS:-${MODELS_DEFAULT}}
INPUTS=${INPUTS:-${INPUTS_DEFAULT}}
VIDEO_FRAMES=${VIDEO_FRAMES:-${VIDEO_FRAMES_DEFAULT}}
TARGET_FPS=${TARGET_FPS:-${TARGET_FPS_DEFAULT}}
MODEL_CONFIG=${MODEL_CONFIG:-percebro/config/model-config.json}

CVCORES=${CVCORES:-$CVCORES_DEFAULT}
OVCORES=${OVCORES:-$OVCORES_DEFAULT}

echo "Models: ${MODELS}"
echo "Inputs: ${INPUTS}"

CMD="percebro/src/percebro"
EXTRA_ARGS="--stats --debug"
INTRINSICS="{\"fov\":70}"

RESULT=0

echo "Processing inputs ${INPUTS}"
CAMID=1
INP_STR=""
for i in ${INPUTS}
do

    INP_STR="${INP_STR} -i ${i} --mqttid camera${CAMID} --intrinsics=${INTRINSICS}"
    CAMID=$(( $CAMID + 1 ))

done

function run_thread_test()
{
    OVCORES=$1
    CVCORES=$2
    CORESSTR="--cvcores ${CVCORES} --ovcores ${OVCORES} "
    ${CMD} ${INP_STR} -m ${MODELS} ${INPUT_LEN} ${CORESSTR} --modelconfig ${MODEL_CONFIG} ${EXTRA_ARGS} \
      --frames ${VIDEO_FRAMES} --stats --waitforstable --preprocess > /dev/null 2>&1 &
    TESTPID=$!

    MAX_WAIT=30
    STARTED=0
    NUMTHREADS=0
    CHECK_DELTA=10
    sleep ${CHECK_DELTA}
    CUR_WAIT=${CHECK_DELTA}
    while [[ $STARTED -eq 0 ]]
    do
        if [[ $CUR_WAIT -ge $MAX_WAIT ]]
        then
          echo "Error: Failed to start ${CONTAINERNAME} container."
          return 1
        fi
        NUMTHREADS=$( ls -l /proc/${TESTPID}/task/ | wc -l )

        if [[ $NUMTHREADS -gt 3 ]]
        then
            STARTED=1
        else
            sleep ${CHECK_DELTA}
            CUR_WAIT=$(( ${CUR_WAIT} + ${CHECK_DELTA} ))
        fi
    done
    kill $TESTPID
    wait $TESTPID
    return $NUMTHREADS
}

run_thread_test 1 1
NUMTHREADS=$?

# Number of threads to start up percebro are what we found minus one for opencv, one for openvino
PERCEBRO_BASE_THREADS=$(( $NUMTHREADS - 2 ))

echo "Number of threads with 1/1 was ${NUMTHREADS}. Base is ${PERCEBRO_BASE_THREADS}"

# Try 2, 4, 8 threads.

TEST_OVCORES=2
TEST_CVCORES=1
run_thread_test ${TEST_OVCORES} ${TEST_CVCORES}
NUMTHREADS=$?

EXPECTED_THREADS=$(( ${PERCEBRO_BASE_THREADS} + ${TEST_OVCORES} + ${TEST_CVCORES} ))
if [[ $EXPECTED_THREADS -ne $NUMTHREADS ]]
then
    echo "Failed test for ${TEST_OVCORES}/${TEST_CVCORES} threads (Expected ${EXPECTED_THREADS} got ${NUMTHREADS})"
    RESULT=1
else
    echo "Test for ${TEST_OVCORES}/${TEST_CVCORES} ok ($NUMTHREADS)"
fi

TEST_OVCORES=4
TEST_CVCORES=1
run_thread_test ${TEST_OVCORES} ${TEST_CVCORES}
NUMTHREADS=$?

EXPECTED_THREADS=$(( ${PERCEBRO_BASE_THREADS} + ${TEST_OVCORES} + ${TEST_CVCORES} ))
if [[ $EXPECTED_THREADS -ne $NUMTHREADS ]]
then
    echo "Failed test for ${TEST_OVCORES}/${TEST_CVCORES} threads (Expected ${EXPECTED_THREADS} got ${NUMTHREADS})"
    RESULT=1
else
    echo "Test for ${TEST_OVCORES}/${TEST_CVCORES} ok ($NUMTHREADS)"
fi


TEST_OVCORES=8
TEST_CVCORES=1
run_thread_test ${TEST_OVCORES} ${TEST_CVCORES}
NUMTHREADS=$?

EXPECTED_THREADS=$(( ${PERCEBRO_BASE_THREADS} + ${TEST_OVCORES} + ${TEST_CVCORES} ))
if [[ $EXPECTED_THREADS -ne $NUMTHREADS ]]
then
    echo "Failed test for ${TEST_OVCORES}/${TEST_CVCORES} threads (Expected ${EXPECTED_THREADS} got ${NUMTHREADS})"
    RESULT=1
else
    echo "Test for ${TEST_OVCORES}/${TEST_CVCORES} ok ($NUMTHREADS)"
fi

TEST_OVCORES=4
TEST_CVCORES=2
run_thread_test ${TEST_OVCORES} ${TEST_CVCORES}
NUMTHREADS=$?

EXPECTED_THREADS=$(( ${PERCEBRO_BASE_THREADS} + ${TEST_OVCORES} + ${TEST_CVCORES} ))
if [[ $EXPECTED_THREADS -ne $NUMTHREADS ]]
then
    echo "Failed test for ${TEST_OVCORES}/${TEST_CVCORES} threads (Expected ${EXPECTED_THREADS} got ${NUMTHREADS})"
    RESULT=1
else
    echo "Test for ${TEST_OVCORES}/${TEST_CVCORES} ok ($NUMTHREADS)"
fi


TEST_OVCORES=8
TEST_CVCORES=2
run_thread_test ${TEST_OVCORES} ${TEST_CVCORES}
NUMTHREADS=$?

EXPECTED_THREADS=$(( ${PERCEBRO_BASE_THREADS} + ${TEST_OVCORES} + ${TEST_CVCORES} ))
if [[ $EXPECTED_THREADS -ne $NUMTHREADS ]]
then
    echo "Failed test for ${TEST_OVCORES}/${TEST_CVCORES} threads (Expected ${EXPECTED_THREADS} got ${NUMTHREADS})"
    RESULT=1
else
    echo "Test for ${TEST_OVCORES}/${TEST_CVCORES} ok ($NUMTHREADS)"
fi


if [[ $RESULT -eq 0 ]]
then
    echo "All thread configurations were successful."
else
    echo "Failed to obtain expected thread configurations."
fi

exit $RESULT
