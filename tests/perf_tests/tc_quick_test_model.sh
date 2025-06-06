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

TEST_NAME="NEX-T10437"
echo "Executing: ${TEST_NAME}"

INPUTS="/workspace/sample_data/apriltag-cam1.mp4"
EXAMPLE_MODEL_CONFIG="/workspace/sample_data/model-config-test.json"
VIDEO_FRAMES=60
STATUS=1

make -C docker install-models MODELS=all

echo "1. Check initial test model from model-config.json."

if [[ $(grep \"test\" percebro/config/model-config.json) == "" ]]
then
    echo "Test model not exist in model-config.json."
    exit $STATUS
fi

docker/scenescape-start cat percebro/config/model-config.json

echo "Testing model: test"
docker/scenescape-start percebro/percebro -m test -i $INPUTS \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats
STATUS=$?

if [[ $STATUS -eq 1 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

echo "2. Copy percebro/config/model-config.json in $EXAMPLE_MODEL_CONFIG."
docker/scenescape-start cp -v percebro/config/model-config.json $EXAMPLE_MODEL_CONFIG

echo "3. Check new model from $EXAMPLE_MODEL_CONFIG."
echo "Rename model test in test_model_new"
docker/scenescape-start sed -i 's/"test"/"test_model_new"/g' $EXAMPLE_MODEL_CONFIG

docker/scenescape-start cat $EXAMPLE_MODEL_CONFIG

echo "Testing model: test_model_new"
docker/scenescape-start percebro/percebro -m test_model_new -i $INPUTS \
                          --modelconfig $EXAMPLE_MODEL_CONFIG \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats
STATUS=$?

if [[ $STATUS -eq 1 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

echo "4. Check new model with other type from $EXAMPLE_MODEL_CONFIG."
echo "Change model type pedestrian-and-vehicle-detector-adas-0001 to person-vehicle-bike-detection-crossroad-1016 from test_model_new"
docker/scenescape-start sed -i 's/"pedestrian-and-vehicle-detector-adas-0001"/"person-vehicle-bike-detection-crossroad-1016"/g' $EXAMPLE_MODEL_CONFIG

docker/scenescape-start cat $EXAMPLE_MODEL_CONFIG

echo "Testing model: test_model_new"
docker/scenescape-start percebro/percebro -m test_model_new -i $INPUTS \
                          --modelconfig $EXAMPLE_MODEL_CONFIG \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats
STATUS=$?

if [[ $STATUS -eq 1 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

docker/scenescape-start rm $EXAMPLE_MODEL_CONFIG

echo "${TEST_NAME}: PASS"
exit $STATUS
