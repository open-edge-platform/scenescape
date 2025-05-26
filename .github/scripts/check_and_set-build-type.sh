#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

# Debug: print key GitHub environment variables
echo "GitHub Event Name: $GITHUB_EVENT_NAME"
echo "GitHub Ref: $GITHUB_REF"
echo "GitHub Workflow: $GITHUB_WORKFLOW"
echo "GitHub Actor: $GITHUB_ACTOR"

# Default build type
BUILD_TYPE="POSTMERGE"

# Detect build type based on event and workflow name
case "$GITHUB_EVENT_NAME" in
  pull_request)
    BUILD_TYPE="PREMERGE"
    ;;
  workflow_dispatch)
    # Manual trigger via UI
    if [[ "$GITHUB_WORKFLOW" == *"DRYRUN"* ]]; then
      BUILD_TYPE="MANUAL"
    elif [[ "$GITHUB_WORKFLOW" == *"RELEASE"* ]]; then
      BUILD_TYPE="TAG"
    fi
    ;;
  schedule)
    # Scheduled builds
    if [[ "$GITHUB_WORKFLOW" == *"DAILY"* ]]; then
      BUILD_TYPE="DAILY"
    elif [[ "$GITHUB_WORKFLOW" == *"WEEKLY"* ]]; then
      BUILD_TYPE="WEEKLY"
    else
      BUILD_TYPE="POSTMERGE"
    fi
    ;;
  push)
    if [[ "$GITHUB_REF" == refs/tags/* ]]; then
      BUILD_TYPE="TAG"
    elif [[ "$GITHUB_REF" == refs/heads/* ]]; then
      # Default for branch pushes
      BUILD_TYPE="POSTMERGE"
    fi
    ;;
esac

# If workflow name includes "RELEASE", treat as a tag build
if [[ "$GITHUB_WORKFLOW" == *"RELEASE"* ]]; then
  BUILD_TYPE="TAG"
fi

# Set BUILD_TYPE for other steps
echo "BUILD_TYPE=$BUILD_TYPE" >> "$GITHUB_ENV"
echo "☛☛☛ Current build type: $BUILD_TYPE ☚☚☚"

# Extract JIRA release version from file
JIRA_RELEASE=$(grep -oP "^\d+\.\d+" sscape/version.txt || echo "unknown")
echo "JIRA_RELEASE=$JIRA_RELEASE" >> "$GITHUB_ENV"
echo "☛☛☛ JIRA_RELEASE set to: $JIRA_RELEASE ☚☚☚"

case "$BUILD_TYPE" in
  TAG)
    VERSION="${GITHUB_REF##*/}"  # Extract tag name
    ARTIFACTORY_PATH="iseaval-ba-local/scenescape/release"
    SW_PACKAGE_DIR="scenescape_${VERSION}"
    TEST_TEMPLATE="R - All Tests"
    ;;
  WEEKLY)
    VERSION="$(date -u +%YWW%W)"
    ARTIFACTORY_PATH="iseaval-ba-local/scenescape/weekly"
    SW_PACKAGE_DIR="scenescape_${VERSION}"
    TEST_TEMPLATE="R - All Tests"
    ;;
  DAILY)
    VERSION="$(date -u +%Y%m%dT%H%M)_${GITHUB_REF##*/}_$(git rev-parse --short HEAD)"
    ARTIFACTORY_PATH="iseaval-ba-local/scenescape/daily"
    SW_PACKAGE_DIR="scenescape"
    TEST_TEMPLATE="T - All Tests"
    ;;
esac

# Export vars for other steps
echo "VERSION=$VERSION" >> "$GITHUB_ENV"
echo "ARTIFACTORY_PATH=$ARTIFACTORY_PATH" >> "$GITHUB_ENV"
echo "SW_PACKAGE_DIR=$SW_PACKAGE_DIR" >> "$GITHUB_ENV"
echo "TEST_TEMPLATE=$TEST_TEMPLATE" >> "$GITHUB_ENV"
