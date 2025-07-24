#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

INPDIR="./sample_data/"
INPUT="apriltag-cam1.mp4"
INPUT2="apriltag-cam2.mp4"
INPUT3="apriltag-cam3.mp4"

JSONFILE=$( echo $INPUT | sed -e 's/mp4/json/g' )
JSONFILE2=$( echo $INPUT2 | sed -e 's/mp4/json/g' )
JSONFILE3=$( echo $INPUT3 | sed -e 's/mp4/json/g' )

VIDEO_FRAMES=1781
PERF_CMD="controller/tools/analytics/trackrate --frame 1500"
CONFIG="tests/perf_tests/config/config.json"
PERF_STR="PERF"

RESULT=0

###############################################
############## SINGLE CAMERA  #################
###############################################

#############################
### SINGLE MODEL (Retail) ###
#############################

echo ""
echo "Single Camera (Retail)"
echo "Running ${PERF_CMD} --config ${CONFIG} ${INPDIR}/${JSONFILE}"
START=$SECONDS
${PERF_CMD} --config ${CONFIG} ${INPDIR}/${JSONFILE} --skip-validation | grep "${PERF_STR}"
RESULT1=$?
END=$SECONDS
CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )
PROCTIME=$(( $END - $START ))
echo "CPU use: $CPUUSE, Wall time ${PROCTIME}"

###############################################
############## DOUBLE CAMERA  #################
###############################################

#############################
### SINGLE MODEL (Retail) ###
#############################

echo ""
echo "Double Camera (Retail)"
echo "Running ${PERF_CMD} --config ${CONFIG} ${INPDIR}/${JSONFILE} ${INPDIR}/${JSONFILE2} --skip-validation "
START=$SECONDS
${PERF_CMD} --config ${CONFIG} ${INPDIR}/${JSONFILE} ${INPDIR}/${JSONFILE2} --skip-validation | grep "${PERF_STR}"
RESULT2=$?
END=$SECONDS
CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )
PROCTIME=$(( $END - $START ))
echo "CPU use: $CPUUSE, Wall time ${PROCTIME}"

###############################################
############## TRIPLE CAMERA  #################
###############################################

#############################
### SINGLE MODEL (Retail) ###
#############################

echo ""
echo "Triple Camera (Retail)"
echo "Running ${PERF_CMD} --config ${CONFIG} ${INPDIR}/${JSONFILE} ${INPDIR}/${JSONFILE2} ${INPDIR}/${JSONFILE3} --skip-validation "
START=$SECONDS
${PERF_CMD} --config ${CONFIG} ${INPDIR}/${JSONFILE} ${INPDIR}/${JSONFILE2} ${INPDIR}/${JSONFILE3} --skip-validation | grep "${PERF_STR}"
RESULT3=$?
END=$SECONDS
CPUUSE=$( cat /proc/loadavg | awk '{print $1}' )
PROCTIME=$(( $END - $START ))
echo "CPU use: $CPUUSE, Wall time ${PROCTIME}"

RESULT=$(( $RESULT1 + $RESULT2 + $RESULT3 ))
exit $RESULT
