#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

INPDIR="/workspace/sample_data"
OUTDIR="/workspace/tests/perf_tests/gen_ref"
BINDIR="/workspace/tests/perf_tests/scripts/"

NUMFRAMES=500
INTRINSICS="{\"fov\":70}"

mkdir -p $OUTDIR

for i in demo
do

    INPUT="${i}-cam1.mp4"
    INPUT2="${i}-cam2.mp4"
    INPUT3="${i}-cam3.mp4"
    OUTPUTFILE=$( echo $INPUT | sed -e 's/mp4/json/g' )
    OUTPUTFILE2=$( echo $INPUT2 | sed -e 's/mp4/json/g' )
    OUTPUTFILE3=$( echo $INPUT3 | sed -e 's/mp4/json/g' )

    rm $OUTPUTFILE $OUTPUTFILE2 $OUTPUTFILE3

    CORESTR="--cvcores 1 --ovcores 10 "

    echo "Generating triple"
    percebro/percebro -i ${INPDIR}/${INPUT} --mqttid camera1  -i ${INPDIR}/${INPUT2} --mqttid camera2 -i ${INPDIR}/${INPUT3} --mqttid camera3 -m retail --intrinsics=${INTRINSICS} --intrinsics=${INTRINSICS} --intrinsics=${INTRINSICS} --debug ${CORESTR} --preprocess  --frames ${NUMFRAMES}

    cp ${INPDIR}/$OUTPUTFILE ${OUTDIR}/xFULLREF_RETAIL_${OUTPUTFILE}
    cp ${INPDIR}/$OUTPUTFILE2 ${OUTDIR}/xFULLREF_RETAIL_${OUTPUTFILE2}
    cp ${INPDIR}/$OUTPUTFILE3 ${OUTDIR}/xFULLREF_RETAIL_${OUTPUTFILE3}

    echo "Generating triple (all)"
    percebro/percebro -i ${INPDIR}/${INPUT} --mqttid camera1  -i ${INPDIR}/${INPUT2} --mqttid camera2 -i ${INPDIR}/${INPUT3} --mqttid camera3 -m apriltag,retail+reid --intrinsics=${INTRINSICS} --intrinsics=${INTRINSICS} --intrinsics=${INTRINSICS} --debug ${CORESTR} --preprocess  --frames ${NUMFRAMES}

    cp ${INPDIR}/$OUTPUTFILE ${OUTDIR}/xFULLREF_ALL_${OUTPUTFILE}
    cp ${INPDIR}/$OUTPUTFILE2 ${OUTDIR}/xFULLREF_ALL_${OUTPUTFILE2}
    cp ${INPDIR}/$OUTPUTFILE3 ${OUTDIR}/xFULLREF_ALL_${OUTPUTFILE3}

    for i in ${OUTDIR}/xFULLREF*
    do
        FNAME=$( echo $i | sed -e 's/xFULLREF/xREF/g' -e 's/json/txt/g' )
        cp $i ${FNAME}

    done

done
