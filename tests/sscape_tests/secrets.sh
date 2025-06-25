#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

export LOGSFORCONTAINER=mqtt_publish_1
export LOG=${LOGSFORCONTAINER}.log
if [ ! -e manager/src/django/secrets.py -a ! -h manager/src/django/secrets.py ] ; then
    echo "Creating symlink to django secrets"
    ln -s /run/secrets/django/secrets.py manager/src/django/
fi
