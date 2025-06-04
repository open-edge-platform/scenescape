#!/bin/bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.
# See the LICENSE file in the root of this repository for details.

set -euo pipefail

echo "Setting environment variables for Makefile logic..."

if [[ -n "${GITHUB_HEAD_REF}" ]]; then
  # Pull request: use source branch
  echo "branch_name=${GITHUB_HEAD_REF}" >> "$GITHUB_OUTPUT"
else
  # Push, tag, manual, schedule: use GITHUB_REF_NAME
  echo "branch_name=${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"
fi

# Log event name for debug
echo "GitHub Event: $GITHUB_EVENT_NAME"

# Set change_target only for PRs
if [[ "$GITHUB_EVENT_NAME" == "pull_request" ]]; then
  CHANGE_TARGET=$(jq -r .pull_request.base.ref "$GITHUB_EVENT_PATH")
  echo "change_target=$CHANGE_TARGET" >> "$GITHUB_OUTPUT"
else
  echo "change_target=" >> "$GITHUB_OUTPUT"
fi
