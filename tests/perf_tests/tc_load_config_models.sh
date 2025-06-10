#!/bin/bash

# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

TEST_NAME="NEX-T10409"
echo "Executing: ${TEST_NAME}"

INPUTS="/workspace/sample_data/apriltag-cam1.mp4"
EXAMPLE_MODEL_CONFIG="sample_data/model-config-test.json"
LOG_1="sample_data/log1.txt"
LOG_2="sample_data/log2.txt"
LOG_3="sample_data/log3.txt"
VIDEO_FRAMES=80
STATUS=1

make -C docker install-models MODELS=all

echo "1. Check initial retail+hpe from model-config.json."

echo "Testing model: retail+hpe without specify modelconfig parameter."
docker/scenescape-start percebro/percebro -m retail+hpe -i $INPUTS \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats &> $LOG_1
STATUS=$?

if [[ $STATUS -ne 0 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

cat $LOG_1

if [[ "$(cat $LOG_1 | awk '{ print $7 }' | grep 4 | uniq)" == "4" ]]
then
    echo -e "Found 4 detection at hpe model.\n"
else
    echo -e "Not found 4 detection at hpe model.\n"
    exit 1
fi

if [[ "$(cat $LOG_1 | awk '{ print $9 }' | grep 4 | uniq)" == "4" ]]
then
    echo -e "Found 4 detection at retail model.\n"
else
    echo -e "Not found 4 detection at retail model.\n"
    exit 1
fi

echo "Testing model: retail+hpe with specify modelconfig parameter."
docker/scenescape-start percebro/percebro -m retail+hpe -i $INPUTS \
                          --modelconfig percebro/config/model-config.json \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats &> $LOG_2
STATUS=$?

if [[ $STATUS -ne 0 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

cat $LOG_2

if [[ "$(cat $LOG_2 | awk '{ print $7 }' | grep 4 | uniq)" == "4" ]]
then
    echo -e "Found 4 detection at hpe model.\n"
else
    echo -e "Not found 4 detection at hpe model.\n"
    exit 1
fi

if [[ "$(cat $LOG_2 | awk '{ print $9 }' | grep 4 | uniq)" == "4" ]]
then
    echo -e "Found 4 detection at retail model.\n"
else
    echo -e "Not found 4 detection at retail model.\n"
    exit 1
fi

echo "2. Execute retail+hpe model from new model config file."

echo -ne '[\n\t {"model": "retail", "engine": "Detector", "keep_aspect": 1, "external_id": "person-detection-retail-0013"},\n
\t {"model": "hpe", "engine": "PoseEstimator", "keep_aspect": 1, "external_id": "human-pose-estimation-0001"}\n]\n' > $EXAMPLE_MODEL_CONFIG

echo "Testing model: retail+hpe with specify modelconfig parameter."
docker/scenescape-start percebro/percebro -m retail+hpe -i $INPUTS \
                          --modelconfig $EXAMPLE_MODEL_CONFIG \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats &> $LOG_3
STATUS=$?

if [[ $STATUS -ne 0 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

cat $LOG_3

if [[ "$(cat $LOG_3 | awk '{ print $7 }' | grep 4 | uniq)" == "4" ]]
then
    echo -e "Found 4 detection at hpe model.\n"
else
    echo -e "Not found 4 detection at hpe model.\n"
    exit 1
fi

if [[ "$(cat $LOG_3 | awk '{ print $9 }' | grep 4 | uniq)" == "4" ]]
then
    echo -e "Found 4 detection at retail model.\n"
else
    echo -e "Not found 4 detection at retail model.\n"
    exit 1
fi

rm $LOG_1 $LOG_2 $LOG_3 $EXAMPLE_MODEL_CONFIG

echo "${TEST_NAME}: PASS"
exit $STATUS
