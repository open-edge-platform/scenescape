#!/bin/bash

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

OUTDIR="./tests/perf_tests/gen_ref"
TGTDIR="${PWD}/tests/perf_tests/references"
docker run -v ${PWD}:/workspace -v ${PWD}/model_installer/models:/opt/intel/openvino/deployment_tools/intel_models/ --privileged -it scenescape tests/perf_tests/scripts/gen_references.sh

pushd ${OUTDIR}
for i in *txt
do
    zip ${i}.zip ${i}
    cp ${i}.zip ${TGTDIR}/
    rm ${i}
done
popd

