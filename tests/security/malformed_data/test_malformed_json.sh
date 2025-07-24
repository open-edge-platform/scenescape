#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

SECURITY_TEST_BASE=tests/security
COMPOSE=tests/compose
BADDATA_TEST_BASE=${SECURITY_TEST_BASE}/malformed_data
rm -rf ${BADDATA_TEST_BASE}/{db,media,migrations}
export SUPASS=admin123
TESTDB=malformed_test_db.tar.bz2
export EXAMPLEDB=${TESTDB}
cp ${BADDATA_TEST_BASE}/${TESTDB} .

export LOGSFORCONTAINER=mqtt_malformed_1
export LOG=${LOGSFORCONTAINER}.log
tests/runtest ${COMPOSE}/broker.yml:${COMPOSE}/mqtt_malformed.yml:${COMPOSE}/ntp.yml:${COMPOSE}/pgserver.yml:${COMPOSE}/scene.yml:${COMPOSE}/web.yml \
              tests/security/malformed_data/baddata_gen.py -i tests/security/malformed_data/baddata_json.txt \
              broker.scenescape.intel.com

RESULT=$?

TEST_NAME="Validate-JSON-files"
if [[ $RESULT -ne 0 ]]
then
    echo "${TEST_NAME}: FAIL"
    exit $RESULT
fi

# baddata_json.txt has the description of GOOD/UNKNOWN/INVALID and the data that is sent down.
INPUT_DATA=baddata_json.txt
EXPECTED_GOOD=$( grep GOOD ${BADDATA_TEST_BASE}/${INPUT_DATA} | awk '{print $3}' | sort -u )
EXPECTED_INVALID=$( grep INVALID ${BADDATA_TEST_BASE}/${INPUT_DATA} | awk '{print $4}' | sort -u )
EXPECTED_UNKNOWN=$( grep UNKNOWN ${BADDATA_TEST_BASE}/${INPUT_DATA} | awk '{print $4}' | sort -u )

TOTAL_EXPECTED=${EXPECTED_GOOD}

TOTAL_FOUND=$( grep 'Msg' ${LOG} | wc -l )
NUM_GOOD_FOUND=0

VAL_FAILED=0

for g in ${EXPECTED_GOOD}
do
    G_FOUND=$( grep "$g " ${LOG} | wc -l )
    NUM_GOOD_FOUND=$(( ${NUM_GOOD_FOUND} + ${G_FOUND} ))

    if [[ ${G_FOUND} -eq 0 ]]
    then
        echo "Failed to receive messages from expected-good sensor $g"
        VAL_FAILED=1
    fi
done

if [[ ${TOTAL_FOUND} -ne ${NUM_GOOD_FOUND} ]]
then
    echo "Received extra 'good' sensors. (Found ${TOTAL_FOUND} messages, but only ${NUM_GOOD_FOUND} come from good sensors."
    VAL_FAILED=1
fi

for i in ${EXPECTED_INVALID}
do
    INV_FOUND=$( grep "$i " ${LOG} | wc -l )

    if [[ ${INV_FOUND} -ne 0 ]]
    then
        echo "Invalid sensor $i was marked as good sensor!"
        VAL_FAILED=1
    fi
done

for u in ${EXPECTED_UNKNOWN}
do
    UNK_FOUND=$( grep "$u " ${LOG} | wc -l )

    if [[ ${UNK_FOUND} -ne 0 ]]
    then
        echo "Unknown sensor $u was marked as good sensor!"
        VAL_FAILED=1
    fi
done

if [[ ${VAL_FAILED} -ne 0 ]]
then
    echo "Test failed validation step. Scene published:"
    cat ${LOG}
    RESULT=1
fi

if [[ $RESULT -eq 0 ]]
then
    echo "${TEST_NAME}: PASS"
    rm -f ${LOG}
else
    echo "${TEST_NAME}: FAIL"
fi

rm ${TESTDB}

exit $RESULT
