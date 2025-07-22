#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

export LOGSFORCONTAINER=mqtt_publish_1
export LOG=${LOGSFORCONTAINER}.log
if [ ! -e manager/src/django/secrets.py -a ! -h manager/src/django/secrets.py ] ; then
    echo "Creating symlink to django secrets"
    ln -s /run/secrets/django/secrets.py manager/src/django/
fi
