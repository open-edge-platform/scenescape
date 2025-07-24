#!/bin/bash

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

TEST_NAME="NEX-T10437"
echo "Executing: ${TEST_NAME}"

INPUTS="/workspace/sample_data/apriltag-cam1.mp4"
EXAMPLE_MODEL_CONFIG="/workspace/sample_data/model-config-test.json"
VIDEO_FRAMES=60
STATUS=1

make -C  ../model_installer install-models MODELS=all

echo "1. Check initial test model from model-config.json."

if [[ $(grep \"test\" percebro/config/model-config.json) == "" ]]
then
    echo "Test model not exist in model-config.json."
    exit $STATUS
fi

tools/scenescape-start cat percebro/config/model-config.json

echo "Testing model: test"
tools/scenescape-start percebro/percebro -m test -i $INPUTS \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats
STATUS=$?

if [[ $STATUS -eq 1 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

echo "2. Copy percebro/config/model-config.json in $EXAMPLE_MODEL_CONFIG."
tools/scenescape-start cp -v percebro/config/model-config.json $EXAMPLE_MODEL_CONFIG

echo "3. Check new model from $EXAMPLE_MODEL_CONFIG."
echo "Rename model test in test_model_new"
tools/scenescape-start sed -i 's/"test"/"test_model_new"/g' $EXAMPLE_MODEL_CONFIG

tools/scenescape-start cat $EXAMPLE_MODEL_CONFIG

echo "Testing model: test_model_new"
tools/scenescape-start percebro/percebro -m test_model_new -i $INPUTS \
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
tools/scenescape-start sed -i 's/"pedestrian-and-vehicle-detector-adas-0001"/"person-vehicle-bike-detection-crossroad-1016"/g' $EXAMPLE_MODEL_CONFIG

tools/scenescape-start cat $EXAMPLE_MODEL_CONFIG

echo "Testing model: test_model_new"
tools/scenescape-start percebro/percebro -m test_model_new -i $INPUTS \
                          --modelconfig $EXAMPLE_MODEL_CONFIG \
                          --intrinsics='{"fov":70}' \
                          --frames $VIDEO_FRAMES --preprocess --stats
STATUS=$?

if [[ $STATUS -eq 1 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $STATUS
fi

tools/scenescape-start rm $EXAMPLE_MODEL_CONFIG

echo "${TEST_NAME}: PASS"
exit $STATUS
