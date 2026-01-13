#!/bin/sh

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

if [ -z "$SCENESCAPE_TOKEN" ]; then
  echo "SCENESCAPE_TOKEN environment variable is not set, trying to obtain a new token..."
  if [ -n "$SUPASS" ]; then
    export SCENESCAPE_TOKEN=$(curl --location --insecure -X POST -d "username=admin&password=$SUPASS" https://localhost/api/v1/auth | jq .token | tr -d '"' )
  else
    echo "SUPASS environment variable is not set, cannot obtain a new token. Exiting."
    exit 1
  fi
fi

curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" https://127.0.0.1/api/v1/regions > regions.json
curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" https://127.0.0.1/api/v1/tripwires > tripwires.json

