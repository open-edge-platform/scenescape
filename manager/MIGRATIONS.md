# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Django Migrations Guide

## Overview

SceneScape uses Django's migration system to manage database schema changes. Migration files are version-controlled and applied at runtime to ensure consistent database upgrades across releases.

## Important: Proper Migration Usage

**DO NOT** run `makemigrations` at runtime or in production. Migrations should be:
1. Generated during development
2. Reviewed and tested
3. Committed to version control
4. Built into the Docker image
5. Applied at runtime via `migrate` only

## Creating Migrations

### For Local Development

When you modify Django models in `src/django/models.py`, follow these steps:

1. **Make your model changes** in `src/django/models.py`

2. **Generate migration file** using the manager container:
   ```bash
   docker compose exec manager python manage.py makemigrations manager
   ```

3. **Review the generated migration** in `src/django/migrations/`:
   ```bash
   ls -la manager/src/django/migrations/
   ```

4. **Test the migration**:
   ```bash
   docker compose exec manager python manage.py migrate
   ```

5. **Check migration status**:
   ```bash
   docker compose exec manager python manage.py showmigrations
   ```

6. **Commit the migration file** to version control:
   ```bash
   git add manager/src/django/migrations/XXXX_*.py
   git commit -m "Add migration for [describe changes]"
   ```

### For CI/CD and Release Process

Migration generation should be automated as part of the release build:

1. **In CI/CD pipeline**, after model changes are merged:
   ```bash
   # Build the manager image
   make manager
   
   # Start a temporary container to generate migrations
   docker compose up -d manager
   docker compose exec manager python manage.py makemigrations --dry-run --check
   
   # If migrations are needed, generate them
   docker compose exec manager python manage.py makemigrations manager
   
   # Copy migrations from container to repository
   docker cp scenescape-manager:/home/scenescape/SceneScape/manager/migrations/. manager/src/django/migrations/
   
   # Commit and push the generated migrations
   git add manager/src/django/migrations/
   git commit -m "Generate migrations for release"
   git push
   ```

2. **Rebuild the image** with the new migrations included

## Migration Naming Convention

Django automatically names migrations as:
- `0001_initial.py` - Initial schema
- `0002_<description>.py` - Subsequent changes
- `0003_<description>.py` - More changes
- etc.

For releases, you may want to include version information in the description:
```bash
docker compose exec manager python manage.py makemigrations manager --name release_2026_1_0
```

This creates: `0002_release_2026_1_0.py`

## Applying Migrations

Migrations are applied automatically at container startup via the `migrate` command in `config/scenescape-init`.

To manually apply migrations:
```bash
docker compose exec manager python manage.py migrate
```

## Checking Migration Status

View all migrations and their application status:
```bash
docker compose exec manager python manage.py showmigrations
```

Example output:
```
manager
 [X] 0001_initial
 [X] 0002_release_2026_1_0
 [ ] 0003_add_new_field
```

## Troubleshooting

### Migration conflicts
If multiple developers create migrations in parallel:
1. Merge the code
2. Run `makemigrations --merge` to create a merge migration
3. Test the merge migration
4. Commit the merge migration file

### Reverting migrations
```bash
# Revert to a specific migration
docker compose exec manager python manage.py migrate manager 0001_initial

# Revert all migrations for an app
docker compose exec manager python manage.py migrate manager zero
```

### Fake migrations
In rare cases (like database schema already matches):
```bash
docker compose exec manager python manage.py migrate manager --fake
```

## Best Practices

1. **Always review generated migrations** before committing
2. **Test migrations** on a copy of production data
3. **Keep migrations small** - one logical change per migration
4. **Never edit applied migrations** - create a new migration instead
5. **Document complex migrations** with comments in the migration file
6. **Backup database** before applying migrations in production

## References

- [Django Migrations Documentation](https://docs.djangoproject.com/en/5.2/topics/migrations/)
- [Django makemigrations Command](https://docs.djangoproject.com/en/5.2/ref/django-admin/#makemigrations)
- [Django migrate Command](https://docs.djangoproject.com/en/5.2/ref/django-admin/#migrate)
