#!/bin/bash

# Copyright (C) 2022 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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

