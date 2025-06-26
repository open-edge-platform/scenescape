#!/bin/sh

# SPDX-FileCopyrightText: (C) 2020 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

FRAMES=1000
DEV=CPU
RDEV=HDDL

LOG=beancount.$$
echo ${DEV} ${RDEV} ${FRAMES} > ${LOG}
for pnum in 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 ; do
    #i=PeopleTest/Slide${pnum}.JPG
    i=PeopleTest/${pnum}.JPG
    echo $i
    echo $i >> ${LOG}
    percebro/percebro -m retail=${DEV}+reid=${RDEV} --debug -i $i --mqttid $i \
                      --stats --frames ${FRAMES} >> ${LOG}
    echo $pnum
done
