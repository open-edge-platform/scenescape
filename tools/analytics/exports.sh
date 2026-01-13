#!/bin/sh

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

if [ -z "$SCENESCAPE_TOKEN" ]; then
    echo "SCENESCAPE_TOKEN environment variable is not set"
    exit 1
fi

curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" https://127.0.0.1/api/v1/regions > regions.json
curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" https://127.0.0.1/api/v1/tripwires > tripwires.json

