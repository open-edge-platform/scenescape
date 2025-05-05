#!/bin/sh

# Copyright (C) 2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

WORKDIR=/tmp/apriltag

mkdir ${WORKDIR}
cd ${WORKDIR}

git clone https://github.com/duckietown/lib-dt-apriltags.git apriltag-dev
cd apriltag-dev
git submodule init
git submodule update
mkdir build
cd build
cmake ../apriltags/
make -j 4
cd ../
pip install .

cp build/*so /usr/local/lib/python3.10/dist-packages/dt_apriltags/

cd
rm -rf ${WORKDIR}
