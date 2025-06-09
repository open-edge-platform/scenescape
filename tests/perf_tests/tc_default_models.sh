#!/bin/bash

# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

TEST_NAME="NEX-T10408"
echo "Executing: ${TEST_NAME}"

MODELS_DEFAULT=(hpe retail pv0078 pv1016 pv0001 v0002 retail+reid tesseract td0001 pv2000 pv2001 pv2002 v0200 v0201 v0202 retail+trresnet)

TESTBASE=tests/perf_tests
INPUTS="${TESTBASE}/input/20_a.JPG"
VIDEO_FRAMES=10
STATUS=1

make -C docker install-models MODELS=all

for model in "${MODELS_DEFAULT[@]}"
do
    echo "Testing model: ${model}"
    docker/scenescape-start percebro/percebro -m $model -i $INPUTS \
                            --modelconfig percebro/config/model-config.json \
                            --intrinsics={\"fov\":70} \
                            --frames $VIDEO_FRAMES --preprocess
    STATUS=$?

    if [[ $STATUS -eq 1 ]]
    then
        echo "${TEST_NAME}: FAIL"
        exit $STATUS
    fi

done;

echo "${TEST_NAME}: PASS"
exit $STATUS
