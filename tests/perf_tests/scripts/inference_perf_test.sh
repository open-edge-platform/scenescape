#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

MODELS_DEFAULT=retail
TESTBASE=tests/perf_tests
INPUTS_DEFAULT="${TESTBASE}/input/20.JPG ${TESTBASE}/input/20_a.JPG"
VIDEO_FRAMES_DEFAULT=1000
TARGET_FPS_DEFAULT=15.0
PERFLOG=/tmp/perf_result.log
PERFLOGFPS=/tmp/perf_result_fps.log
CPU_DECODE_DEFAULT=0

CVCORES_DEFAULT=1
OVCORES_DEFAULT=4

MODELS=${MODELS:-${MODELS_DEFAULT}}
INPUTS=${INPUTS:-${INPUTS_DEFAULT}}
VIDEO_FRAMES=${VIDEO_FRAMES:-${VIDEO_FRAMES_DEFAULT}}
TARGET_FPS=${TARGET_FPS:-${TARGET_FPS_DEFAULT}}
MODEL_CONFIG=${MODEL_CONFIG:-percebro/config/model-config.json}
CPU_DECODE=${CPU_DECODE:-${CPU_DECODE_DEFAULT}}

CVCORES=${CVCORES:-$CVCORES_DEFAULT}
OVCORES=${OVCORES:-$OVCORES_DEFAULT}

echo "Models: ${MODELS}"
echo "Inputs: ${INPUTS}"
echo "Frames: ${VIDEO_FRAMES}"
echo "TARGET FPS: ${TARGET_FPS}"
echo "Using ${CVCORES} cores for OpenCV and ${OVCORES} cores for OpenVINO"


CMD="percebro/src/percebro"
CORESSTR="--cvcores ${CVCORES} --ovcores ${OVCORES} "
EXTRA_ARGS="--stats --debug"
INTRINSICS="{\"fov\":70}"

echo "Processing inputs ${INPUTS}"
CAMID=1
INP_STR=""
for i in ${INPUTS}
do

    INP_STR="${INP_STR} -i ${i} --mqttid camera${CAMID} --intrinsics=${INTRINSICS}"
    CAMID=$(( $CAMID + 1 ))

done

START=$SECONDS
CMD_OPTS="${INP_STR} -m ${MODELS} ${INPUT_LEN} ${CORESSTR} --modelconfig ${MODEL_CONFIG} ${EXTRA_ARGS} --frames ${VIDEO_FRAMES} --stats --preprocess --faketime"
if [[ $CPU_DECODE -ne 0 ]]
then
  CMD_OPTS="${CMD_OPTS} --cpu-decode"
fi
echo Running "${CMD} ${CMD_OPTS}"
${CMD} ${CMD_OPTS}  2> ${PERFLOG}
STATUS=$?
if [ $STATUS != 0 ] ; then
    exit $STATUS
fi
END=$SECONDS
CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )

CAMNAMEOFFSET=5
CAMOFFSET=3

cat ${PERFLOG} | sed -e 's/\x0d/\n/g' | tail -n 2 | head -n 1 > ${PERFLOGFPS}

# We check here that all of the streams achieved the requested FPS.
RESULT=0
CUR_CAM=1
while [[ $CUR_CAM -lt $CAMID ]]
do

    FPSCURCHECK=$(( $CAMNAMEOFFSET + ($CUR_CAM * $CAMOFFSET) ))

    CAMNAME=$( cat ${PERFLOGFPS} | awk "{print \$$FPSCURCHECK}" )

    FPSCURCHECK=$(( $FPSCURCHECK + 2 ))
    CAMFPS=$( cat ${PERFLOGFPS} | awk "{print \$$FPSCURCHECK}" )

    echo "CAM $CAMNAME got $CAMFPS"

    CURRESULT=$( awk -v ft="${TARGET_FPS}" -v fr="$FPS" 'BEGIN {printf (fr>=ft?0:1)}' )
    RESULT=$(( $RESULT + $CURRESULT ))

    CUR_CAM=$(( $CUR_CAM + 1 ))
done

TOTFPS=$( cat ${PERFLOGFPS} | sed -e 's/\x1b.\{4\}//' | awk '{print $2}' )
echo "TOTAL FPS: $TOTFPS"
FPS=$( awk "BEGIN {print ${TOTFPS} / ($CAMID - 1) }" )

PROCTIME=$(( ${END} - ${START} ))

echo ""
echo ""
echo "Achieved $FPS fps per camera, $TOTFPS total, threads used: ${NUMTHREADS} Test CPU load: ${CPUUSE}"

RESULT=$( awk -v ft="${TARGET_FPS}" -v fr="$TOTFPS" 'BEGIN {printf (fr>=ft?0:1)}' )

if [[ $RESULT -eq 0 ]]
then
    echo "Reached at least ${TARGET_FPS} fps!"
else
    echo "Failed to reach minimum FPS!"
fi

exit $RESULT
