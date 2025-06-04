#!/bin/sh
# Copyright (C) 2020-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
