# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# CI/CD Integration for Django Migrations

## Overview

This document describes how to integrate Django migration generation into the SceneScape CI/CD pipeline.

## Problem

Previously, Django migrations were generated at runtime using `makemigrations` in the `scenescape-init` script. This is incorrect because:

1. **Not upgradeable**: Migrations must exist before deployment to support database schema upgrades
2. **Not reproducible**: Running `makemigrations` at runtime can produce different results
3. **Not version-controlled**: Migration files should be tracked in Git
4. **Business continuity issue**: Requires undeployment before installing new versions

## Solution

Migration files are now:
1. Generated during development or in CI/CD
2. Reviewed and committed to version control
3. Built into the Docker image
4. Applied at runtime using only `migrate` (not `makemigrations`)

## CI/CD Pipeline Integration

### Option 1: Pre-Commit Hook (Recommended for Developers)

Add a pre-commit check to ensure migrations are generated when models change:

```yaml
# .github/workflows/check-migrations.yml
name: Check Django Migrations

on: [pull_request]

jobs:
  check-migrations:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker
        uses: docker/setup-buildx-action@v3
        
      - name: Build manager image
        run: make manager
        
      - name: Check for missing migrations
        run: |
          docker compose up -d manager
          sleep 10
          if docker compose exec -T manager python manage.py makemigrations --dry-run --check manager; then
            echo "✓ All migrations are up to date"
          else
            echo "❌ Migrations are missing! Please run: ./manager/tools/generate_migrations.sh"
            exit 1
          fi
```

### Option 2: Automated Migration Generation (CI)

Automatically generate and commit migrations when models change:

```yaml
# .github/workflows/auto-generate-migrations.yml
name: Auto-Generate Django Migrations

on:
  push:
    branches: [main, develop]
    paths:
      - 'manager/src/django/models.py'
      - 'manager/src/django/fields.py'

jobs:
  generate-migrations:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          
      - name: Set up Docker
        uses: docker/setup-buildx-action@v3
        
      - name: Build manager image
        run: make manager
        
      - name: Generate migrations
        run: |
          docker compose up -d manager
          sleep 10
          
          # Check if migrations are needed
          if docker compose exec -T manager python manage.py makemigrations --dry-run --check manager; then
            echo "No migrations needed"
            exit 0
          fi
          
          # Generate migrations
          docker compose exec -T manager python manage.py makemigrations manager --no-input
          
          # Copy migrations from container to host
          docker compose exec -T manager find /home/scenescape/SceneScape/manager/migrations -name "*.py" -newer /tmp/build-start -exec cat {} \; > /tmp/new_migration.py
          
      - name: Commit migrations
        run: |
          git config user.name "GitHub Actions Bot"
          git config user.email "actions@github.com"
          git add manager/src/django/migrations/
          git commit -m "Auto-generate Django migrations [skip ci]" || echo "No changes to commit"
          git push
```

### Option 3: Release Branch Automation

Generate migrations as part of the release preparation:

```yaml
# .github/workflows/prepare-release.yml
name: Prepare Release

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Release version (e.g., 2026.1.0)'
        required: true

jobs:
  prepare-release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Build images
        run: make build-core
        
      - name: Generate migrations with version tag
        run: |
          docker compose up -d manager
          sleep 10
          docker compose exec -T manager python manage.py makemigrations manager --name "release_${{ github.event.inputs.version }}" --no-input
          
      - name: Create release PR
        uses: peter-evans/create-pull-request@v5
        with:
          commit-message: "Prepare release ${{ github.event.inputs.version }}"
          title: "Release ${{ github.event.inputs.version }}"
          body: |
            ## Release ${{ github.event.inputs.version }}
            
            This PR includes:
            - Generated Django migrations
            - Version bump
            
          branch: "release/${{ github.event.inputs.version }}"
```

## Manual Process (Fallback)

If CI/CD automation is not yet implemented, follow this manual process:

1. **Before merging model changes**:
   ```bash
   # Build and start services
   make build-core
   docker compose up -d
   
   # Generate migrations
   ./manager/tools/generate_migrations.sh
   
   # Review generated files
   git diff manager/src/django/migrations/
   
   # Test migrations
   docker compose exec manager python manage.py migrate
   docker compose exec manager python manage.py showmigrations
   
   # Commit
   git add manager/src/django/migrations/
   git commit -m "Add migrations for [describe changes]"
   git push
   ```

2. **During release**:
   - Ensure all migration files are committed
   - Rebuild Docker image (migrations will be included)
   - Deploy new image
   - Migrations apply automatically at startup

## Verification

After implementing CI/CD integration, verify:

1. **No runtime makemigrations**: Check `manager/config/scenescape-init` does NOT contain `makemigrations`
2. **Migrations in image**: Check Docker image contains `/home/scenescape/SceneScape/manager/migrations/`
3. **Migrations in Git**: Check `manager/src/django/migrations/` has version-controlled `.py` files
4. **Clean upgrades**: Test upgrading from previous release without data loss

## Migration File Naming

For releases, use descriptive names with version info:
```bash
docker compose exec manager python manage.py makemigrations manager --name "release_2026_1_0"
```

This creates files like:
- `0001_initial.py`
- `0002_release_2026_1_0.py`
- `0003_release_2026_2_0.py`

## Troubleshooting

### "No changes detected" but models were modified
- Check that changes are in `manager/src/django/models.py`
- Ensure manager service has the latest code mounted
- Restart manager service: `docker compose restart manager`

### Migration conflicts between branches
1. Merge branches
2. Run: `docker compose exec manager python manage.py makemigrations --merge`
3. Commit the merge migration

### Existing deployments without migrations
If deployed before this fix:
1. Generate initial migration
2. Mark it as applied: `docker compose exec manager python manage.py migrate --fake manager 0001`
3. Future migrations will apply normally

## References

- [Django Migrations Documentation](https://docs.djangoproject.com/en/5.2/topics/migrations/)
- [Manager MIGRATIONS.md](./MIGRATIONS.md) - Developer guide
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
