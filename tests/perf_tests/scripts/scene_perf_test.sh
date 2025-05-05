#!/bin/bash

# Copyright (C) 2021-2022 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
