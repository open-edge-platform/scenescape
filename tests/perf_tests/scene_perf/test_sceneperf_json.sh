#!/bin/bash

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

PERF_TEST_BASE=tests/perf_tests
SCENEPERF_TEST_BASE=${PERF_TEST_BASE}/scene_perf
COMPOSE=tests/compose

TEST_NAME="Scene Performance test"

source tests/test_utils.sh

VERSION=$(cat sscape/version.txt)
export BROWSER_IMAGE="scenescape:${VERSION}"
export IMAGE="scenescape:${VERSION}"

TESTINPUTRATE=${INPUT_RATE:-30}
TESTINPUTFRAMES=${INPUT_FRAMES:-1000}
TESTINPUTFILES=${INPUT_FILES:-"${SCENEPERF_TEST_BASE}/data/amcrest01.json"}
TESTMONITORINTERVAL=${MONITORINTERVAL:-3}

export SCENETEST_INPUTRATE=${TESTINPUTRATE}
export SCENETEST_INPUTFRAMES=${TESTINPUTFRAMES}
export SCENETEST_MONITORINTERVAL=${TESTMONITORINTERVAL}
export SCENETEST_INPUTS=${TESTINPUTFILES}

export LOG=test_mqtt_recorder_log.txt

export SECRETSDIR=/workspace/secrets
export DBROOT=test_data/scene_perf_full

export WAITFORCONTAINERS="pgserver web scene "
export LOGSFORCONTAINER="${WAITFORCONTAINERS} mqtt_recorder "

rm -f ${LOG}
tests/runtest ${COMPOSE}/broker.yml:${COMPOSE}/mqtt_recorder.yml:${COMPOSE}/ntp.yml:${COMPOSE}/pgserver.yml:${COMPOSE}/scene.yml:${COMPOSE}/web.yml \
              percebro/percsim ${TESTINPUTFILES} \
              --auth ${SECRETSDIR}/percebro.auth \
              --rootcert ${SECRETSDIR}/certs/scenescape-ca.pem \
              --rate ${TESTINPUTRATE} \
              --frames ${TESTINPUTFRAMES} --loop

RESULT=$?

if [[ $RESULT -eq 0 ]]
then
    echo "${TEST_NAME}: Test Passed"
else
    echo "${TEST_NAME}: Test Failed"
fi

exit $RESULT
