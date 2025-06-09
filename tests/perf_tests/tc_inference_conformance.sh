#!/bin/bash

# Copyright (C) 2021-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

TEST_NAME="NEX-T10413"
echo "Executing: ${TEST_NAME}"

TESTBASE="tests/perf_tests/"

REFDIR="${TESTBASE}/references"
COMPOSEDIR="${TESTBASE}/compose"
YMLFILE="docker-compose-inference_conformance.yml"

#Extract the reference files:
for i in ${REFDIR}/xREF*.zip
do
    unzip -o $i  -d sample_data/
done

#Run the test...
docker compose -f ${COMPOSEDIR}/${YMLFILE} --project-directory ${PWD} run test

RESULT=$?

if [[ $RESULT -eq 0 ]]
then
    echo "${TEST_NAME}: PASS"
    rm -f xOUT*txt xOUT*json xREF*txt
else
    echo "${TEST_NAME}: FAIL"
fi

exit $RESULT

