#!/bin/bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.
# See the LICENSE file in the root of this repository for details.

set -euo pipefail

# GitHub environment variables
echo "GitHub Event Name: ${GITHUB_EVENT_NAME:-<unset>}"
echo "GitHub Run Type: ${RUN_TYPE:-<unset>}"
echo "GitHub Ref: ${GITHUB_REF:-<unset>}"
echo "GitHub Actor: ${GITHUB_ACTOR:-<unset>}"

# Initialize default build type
BUILD_TYPE="POSTMERGE"

error_exit() {
    echo "ERROR: $1" >&2
    exit 1
}

# Detect build type
case "${GITHUB_EVENT_NAME:-}" in
  pull_request)
    BUILD_TYPE="PREMERGE"
    ;;
  workflow_dispatch)
    [[ -z "${RUN_TYPE:-}" ]] && error_exit "RUN_TYPE is required for workflow_dispatch"
    case "$RUN_TYPE" in
      manual)
        BUILD_TYPE="MANUAL"
        ;;
      *)
        error_exit "Invalid RUN_TYPE='$RUN_TYPE'. Expected: 'manual'"
        ;;
    esac
    ;;
  schedule)
    TZ="America/Los_Angeles"
    DAY_OF_WEEK=$(date +%u)  # 1 = Monday, ..., 7 = Sunday
    HOUR=$(date +%H) # 00 to 23 (UTC)

    if [[ "$DAY_OF_WEEK" == "6" && "$HOUR" -ge 12 ]]; then
      BUILD_TYPE="WEEKLY"
    else
      BUILD_TYPE="DAILY"
    fi
    ;;
  push)
    case "${GITHUB_REF:-}" in
      refs/tags/*)
        BUILD_TYPE="TAG"
        ;;
      refs/heads/*)
        BUILD_TYPE="POSTMERGE"
        ;;
      *)
        echo "Unrecognized GITHUB_REF format: '$GITHUB_REF'"
        BUILD_TYPE="UNKNOWN"
        ;;
    esac
    ;;
esac

# Set BUILD_TYPE for other steps
echo "build_type=$BUILD_TYPE" >> "$GITHUB_OUTPUT"
echo "☛☛☛ Current build type: $BUILD_TYPE ☚☚☚"

# Extract JIRA release version from file
JIRA_RELEASE=$(grep -oP "^\d+\.\d+" version.txt || echo "unknown")
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
  *)
    VERSION="unset-${BUILD_TYPE,,}-$(date -u +%s)"
    ARTIFACTORY_PATH="undefined_path-$(date -u +%s)"
    SW_PACKAGE_DIR="undefined_directory-$(date -u +%s)"
    TEST_TEMPLATE="undefined_template-$(date -u +%s)"
    ;;
esac

# Export vars for other steps
echo "VERSION=$VERSION" >> "$GITHUB_ENV"
echo "ARTIFACTORY_PATH=$ARTIFACTORY_PATH" >> "$GITHUB_ENV"
echo "SW_PACKAGE_DIR=$SW_PACKAGE_DIR" >> "$GITHUB_ENV"
echo "TEST_TEMPLATE=$TEST_TEMPLATE" >> "$GITHUB_ENV"
