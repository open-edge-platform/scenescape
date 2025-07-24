#!/bin/sh

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

IMAGE=$1
TEST_NAME="NEX-T10482"
FAIL=0

# openvino Dockerfiles located here:
#   https://github.com/openvinotoolkit/docker_ci/tree/master/dockerfiles

if [ -z "${IMAGE}" ] ; then
    echo Please specify openvino image to test
    exit 1
fi

docker image inspect ${IMAGE} >/dev/null 2>&1
if [ $? -ne 0 ] ; then
    docker pull ${IMAGE}
    if [ $? -ne 0 ] ; then
        echo '#################'
        echo IMAGE DOES NOT EXIST
        echo $TEST_NAME: FAIL
        echo '#################'
        exit 1
    fi
fi

# Make sure RTSP is included
docker run --rm ${IMAGE} /bin/bash -c 'env -i $(source /opt/intel/openvino/bin/setupvars.sh \
       2>/dev/null >/dev/null && env | grep ^LD_LIBRARY_PATH=) gst-inspect-1.0' 2>/dev/null \
    | egrep -iq '^rtsp'
if [ $? -ne 0 ] ; then
    echo '###################'
    echo $TEST_NAME: FAIL
    echo '###################'
    echo gstreamer is not correctly built
    echo Please fix image to use correctly compiled gstreamer
    FAIL=1
else
    echo $TEST_NAME: PASS
fi

exit ${FAIL}
