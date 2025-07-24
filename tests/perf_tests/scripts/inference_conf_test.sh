#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

CVCORES_DEFAULT=1
OVCORES_DEFAULT=4
CONFORMANCE_CHECK=${CONFORMANCE_CHECK:-YES}
CHECK_REID=${CHECK_REID:-NO}

CVCORES=${CVCORES:-$CVCORES_DEFAULT}
OVCORES=${OVCORES:-$OVCORES_DEFAULT}

echo "Using ${CVCORES} cores for OpenCV and ${OVCORES} cores for OpenVINO"
echo "Conformance check ${CONFORMANCE_CHECK}"

echo "Using REID model: ${CHECK_REID}"

NUM_FRAMES=500
CMD="percebro/src/percebro"
CORESSTR="--cvcores ${CVCORES} --ovcores ${OVCORES} "
MODEL_CONFIG="percebro/config/model-config.json"
EXTRA_ARGS="--stats --debug --frames ${NUM_FRAMES}"

INPDIR="./sample_data/"
INPUT="apriltag-cam1.mp4"
INPUT2="apriltag-cam2.mp4"
INPUT3="apriltag-cam3.mp4"
VIDEO_FRAMES=1789

INTRINSICS="{\"fov\":70}"

OUTPUTFILE=$( echo $INPUT | sed -e 's/mp4/json/g' )
OUTPUTFILE2=$( echo $INPUT2 | sed -e 's/mp4/json/g' )
OUTPUTFILE3=$( echo $INPUT3 | sed -e 's/mp4/json/g' )

EXTRA_ARGS="${EXTRA_ARGS} --preprocess"
INPUT_LEN=""

PROCESS_CMD="tests/perf_tests/scripts/process_result"

RESULT=0

function compare_output_to_ref() {
    OUTFILE=$1
    RUNTYPE=$2
    REFTYPE=$3

    REFFILE=$( echo ${OUTFILE} | sed -e 's/json/txt/g' -e "s/^/xREF_${REFTYPE}_/g" )
    OUTPROCFILE=$( echo ${OUTFILE} | sed -e 's/json/txt/g' -e "s/^/xOUT_${RUNTYPE}_/g" )

    echo "Comparing output vs ref ${REFFILE}"

    ${PROCESS_CMD} -i ${INPDIR}/${OUTFILE}  -r ${INPDIR}/${REFFILE} --precision 3

    if [[ $?  -ne 0 ]]
    then
        echo "Error in ${OUTPROCFILE} vs ${REFFILE}"
        mv ${INPDIR}/${OUTFILE} ${INPDIR}/xOUT_${RUNTYPE}_${OUTFILE}
        return 1
    else
        echo "${OUTFILE} ok"
        rm ${INPDIR}/${OUTFILE} ${INPDIR}/${OUTPROCFILE} -f
        return 0
    fi
}


###############################################
############## SINGLE CAMERA  #################
###############################################

#############################
### SINGLE MODEL (Retail) ###
#############################

echo ""
echo "Single Camera / Single Model : Performing inference on ${INPUT}"

START=$SECONDS
VAL=$( ${CMD} -i ${INPDIR}/${INPUT} --mqttid camera1 --intrinsics=${INTRINSICS} -m retail ${INPUT_LEN} ${CORESSTR} --modelconfig ${MODEL_CONFIG} ${EXTRA_ARGS} > /dev/null 2>&1 )
END=$SECONDS
CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )

echo "Inference done"

if [[ "${CONFORMANCE_CHECK}" == "YES" ]]
then

    compare_output_to_ref ${OUTPUTFILE} "SINGLE" "RETAIL"
    RESULT=$?

fi


###############################################
############## DOUBLE CAMERA  #################
###############################################

#############################
### SINGLE MODEL (Retail) ###
#############################

echo ""
echo "Dual Camera / Single Model : "

START=$SECONDS
VAL=$( ${CMD} -i ${INPDIR}/${INPUT} --mqttid camera1  --intrinsics=${INTRINSICS} -i ${INPDIR}/${INPUT2} --mqttid camera2  --intrinsics=${INTRINSICS} -m retail ${INPUT_LEN} ${CORESSTR} --modelconfig ${MODEL_CONFIG}  ${EXTRA_ARGS} > /dev/null 2>&1 )
END=$SECONDS
CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )

echo "Inference done"

if [[ "${CONFORMANCE_CHECK}" == "YES" ]]
then

    OUTPUTFILES="${OUTPUTFILE} ${OUTPUTFILE2}"
    RESULT=0
    for OUTFILE in $OUTPUTFILES
    do
        compare_output_to_ref ${OUTFILE} "DOUBLE" "RETAIL"

        if [[ $?  -ne 0 ]]
        then
            RESULT=1
        fi
    done

fi


#############################
### DOUBLE MODEL (Retail) ###
#############################

if [[ "${CHECK_REID}" == "YES" ]]
then

    echo ""
    echo "Dual Camera / Dual Model : "

    START=$SECONDS
    VAL=$( ${CMD} -i ${INPDIR}/${INPUT} --mqttid camera1 --intrinsics=${INTRINSICS} -i ${INPDIR}/${INPUT2} --mqttid camera2 --intrinsics=${INTRINSICS} -m retail+reid ${INPUT_LEN} ${CORESSTR} --modelconfig ${MODEL_CONFIG}  ${EXTRA_ARGS} > /dev/null 2>&1 )
    END=$SECONDS
    CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )


    if [[ "${CONFORMANCE_CHECK}" == "YES" ]]
    then

        OUTPUTFILES="${OUTPUTFILE} ${OUTPUTFILE2}"
        RESULT=0
        for OUTFILE in $OUTPUTFILES
        do
            compare_output_to_ref ${OUTFILE} "DOUBLE" "REID"

            if [[ $?  -ne 0 ]]
            then
                RESULT=1
            fi
        done

    fi


fi

###############################################
############## TRIPLE CAMERA  #################
###############################################

#############################
### SINGLE MODEL (Retail) ###
#############################

echo ""
echo "Triple Camera / Single Model : "

START=$SECONDS
VAL=$( ${CMD} -i ${INPDIR}/${INPUT} --mqttid camera1 --intrinsics=${INTRINSICS} -i ${INPDIR}/${INPUT2} --mqttid camera2 --intrinsics=${INTRINSICS} -i ${INPDIR}/${INPUT3} --mqttid camera3 --intrinsics=${INTRINSICS} -m retail ${INPUT_LEN} ${CORESSTR} --modelconfig ${MODEL_CONFIG}  ${EXTRA_ARGS} > /dev/null 2>&1  )
END=$SECONDS
CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )


if [[ "${CONFORMANCE_CHECK}" == "YES" ]]
then

    OUTPUTFILES="${OUTPUTFILE} ${OUTPUTFILE2} ${OUTPUTFILE3}"
    RESULT=0
    for OUTFILE in $OUTPUTFILES
    do
        compare_output_to_ref ${OUTFILE} "TRIPLE" "RETAIL"

        if [[ $?  -ne 0 ]]
        then
            RESULT=1
        fi
    done

fi


#############################################
### ALL MODELS (APRILTAG, RETAIL + REID ) ###
#############################################

if [[ "${CHECK_ALL}" == "YES" ]]
then

    echo ""
    echo "Triple Camera / Triple Model :"

    START=$SECONDS
    VAL=$( ${CMD} -i ${INPDIR}/${INPUT} --mqttid camera1 --intrinsics=${INTRINSICS} -i ${INPDIR}/${INPUT2} --mqttid camera2 --intrinsics=${INTRINSICS} -i ${INPDIR}/${INPUT3} --mqttid camera3 --intrinsics=${INTRINSICS} -m apriltag,retail+reid  ${INPUT_LEN} ${CORESSTR} --modelconfig ${MODEL_CONFIG}  ${EXTRA_ARGS} > /dev/null 2>&1  )
    END=$SECONDS
    CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )

    if [[ "${CONFORMANCE_CHECK}" == "YES" ]]
    then

        OUTPUTFILES="${OUTPUTFILE} ${OUTPUTFILE2} ${OUTPUTFILE3}"
        RESULT=0
        for OUTFILE in $OUTPUTFILES
        do
            compare_output_to_ref ${OUTFILE} "TRIPLE" "ALL"

            if [[ $?  -ne 0 ]]
            then
                RESULT=1
            fi
        done

    fi


fi

exit $RESULT
