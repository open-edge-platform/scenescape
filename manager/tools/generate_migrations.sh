#!/bin/bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Script to generate Django migrations
# This should be run during development or as part of the release process
# DO NOT run this in production or at container startup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "==> Django Migration Generator for SceneScape Manager"
echo ""

# Check if docker compose is available
if ! command -v docker &> /dev/null; then
  echo "ERROR: docker command not found. Please install Docker."
  exit 1
fi

# Check if manager service is running
if ! docker compose ps manager | grep -q "Up"; then
  echo "WARNING: Manager service is not running."
  echo "Starting manager service..."
  docker compose up -d manager
  sleep 5
fi

echo "Checking if migrations are needed..."
if docker compose exec -T manager python manage.py makemigrations --dry-run --check manager 2>&1 | grep -q "No changes detected"; then
  echo "✓ No migrations needed. Models are up to date."
  exit 0
fi

echo ""
echo "Changes detected. Generating migrations..."
docker compose exec -T manager python manage.py makemigrations manager

echo ""
echo "==> Migration files generated in manager/src/django/migrations/"
echo ""
echo "Next steps:"
echo "1. Review the generated migration files"
echo "2. Test migrations with: docker compose exec manager python manage.py migrate"
echo "3. Check status with: docker compose exec manager python manage.py showmigrations"
echo "4. Commit migration files to version control"
echo ""
