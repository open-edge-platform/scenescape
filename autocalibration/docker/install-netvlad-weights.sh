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

if pip3 show third_party > /dev/null 2>&1; then
    echo "NetVLAD weights are already installed. Skipping installation."
    exit 0
fi

WORKDIR=/tmp/weights_data

mkdir ${WORKDIR}
cd ${WORKDIR}
mkdir third_party
mkdir third_party/netvlad

touch third_party/__init__.py
touch third_party/netvlad/__init__.py

curl -Lo third_party/netvlad/VGG16-NetVLAD-Pitts30K.mat \
    https://cvg-data.inf.ethz.ch/hloc/netvlad/Pitts30K_struct.mat

echo "include third_party/netvlad/*" > MANIFEST.in

cat > setup.py <<EOL
from setuptools import setup, find_packages

setup(
    name='third_party',
    version='1.0.0',
    packages=find_packages(),
    package_data={'': ['VGG16-NetVLAD-Pitts30K.mat']},
    include_package_data=True,
)
EOL

python3 setup.py bdist_wheel
cd dist
pip3 install --no-cache-dir ./*.whl

cd
rm -rf ${WORKDIR}
