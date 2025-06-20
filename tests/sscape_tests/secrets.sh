#!/bin/bash

# Copyright (C) 2021 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

export LOGSFORCONTAINER=mqtt_publish_1
export LOG=${LOGSFORCONTAINER}.log
if [ ! -e manager/src/django/secrets.py -a ! -h manager/src/django/secrets.py ] ; then
    echo "Creating symlink to django secrets"
    ln -s /run/secrets/django/secrets.py manager/src/django/
fi
