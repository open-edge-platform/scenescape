#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

WORKSPACE=${GITHUB_WORKSPACE:-$(pwd)}
echo "Workspace is: $WORKSPACE"

# Set directory to clone into (use AUTOLM_DIR or fallback)
AUTOLM_DIR="${AUTOLM_DIR:-autolm-scripts}"
REPO_URL="https://github.com/intel-innersource/applications.automotive.ci.automation-scripts"
BRANCH="main"
TAG="v1.1.0"

echo "Cloning AutoLM scripts into: $AUTOLM_DIR"

# Clean existing dir if present
rm -rf "$AUTOLM_DIR"

# Clone and checkout specific tag
git clone --branch "$BRANCH" "$REPO_URL" "$AUTOLM_DIR"
cd "$AUTOLM_DIR"
git checkout "$TAG"

echo "✅ AutoLM scripts checked out to $AUTOLM_DIR at tag $TAG"
