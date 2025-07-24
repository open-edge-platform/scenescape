#!/bin/bash

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

TEST_NAME="NEX-T10408"
echo "Executing: ${TEST_NAME}"

MODELS_DEFAULT=(hpe retail pv0078 pv1016 pv0001 v0002 retail+reid tesseract td0001 pv2000 pv2001 pv2002 v0200 v0201 v0202 retail+trresnet)

TESTBASE=tests/perf_tests
INPUTS="${TESTBASE}/input/20_a.JPG"
VIDEO_FRAMES=10
STATUS=1

make -C  ../model_installer install-models MODELS=all

for model in "${MODELS_DEFAULT[@]}"
do
    echo "Testing model: ${model}"
    tools/scenescape-start percebro/percebro -m $model -i $INPUTS \
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
