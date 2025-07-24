#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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

