<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Manager Service - AI Agent Guide

## Service Overview

The **Manager** service is the Django-based web UI and REST API gateway for Intel® SceneScape. It provides user-facing interfaces for system configuration, scene management, camera setup, and PostgreSQL-backed persistence for metadata and configuration.

**Primary Purpose**: Web interface and REST API for managing SceneScape configuration, user authentication, and metadata persistence.

## Architecture & Components

### Core Modules

1. **Django Application** (`src/django/`):
   - Scene management views and APIs
   - Camera configuration interfaces
   - User authentication and authorization
   - PostgreSQL ORM models

2. **REST API** (`src/django/api/`):
   - RESTful endpoints for external integrations
   - Scene CRUD operations
   - Camera calibration triggers
   - Object query endpoints

3. **Management Commands** (`src/management/`):
   - Database migrations
   - Admin utilities
   - Data import/export tools

4. **Static Assets** (`src/static/`):
   - Frontend JavaScript/CSS
   - UI components
   - Visualization tools

5. **Templates** (`src/templates/`):
   - Django HTML templates
   - Web UI pages

### Dependencies

- **Django**: Web framework (Python)
- **PostgreSQL**: Database for metadata persistence
- **Scene Common**: REST client, MQTT utilities
- **Scene Controller**: Backend service for runtime state
- **Gunicorn**: WSGI server for production deployment

## Communication Patterns

### REST API

**Base URL**: `https://manager:8000/api/v1/`

**Authentication**:

- Session-based for web UI
- Token-based for API clients
- TLS mutual auth for service-to-service

**Key Endpoints**:

- `/api/v1/scenes/`: Scene management (CRUD)
- `/api/v1/cameras/`: Camera configuration
- `/api/v1/calibration/`: Trigger calibration
- `/api/v1/objects/`: Query tracked objects
- `/api/v1/health/`: Health check

### Database Schema

**Key Tables**:

- `scenes`: Scene definitions (name, floor plan, coordinate system)
- `cameras`: Camera metadata (ID, position, calibration status)
- `users`: Authentication and permissions
- `audit_log`: System event logging

**Important**: Manager stores **metadata only**—no video streams or real-time object positions. Runtime state lives in Scene Controller.

### MQTT Integration

- Manager can trigger operations via REST → Scene Controller → MQTT
- Does not directly subscribe to MQTT topics
- Uses Scene Controller as intermediary for real-time events

## Development Workflows

### Building the Service

```bash
# From root directory
make manager                            # Build image
make rebuild-manager                    # Clean + rebuild

# Build with dependencies
make build-core                         # Includes manager
```

### Database Migrations

```bash
# Create migration after model changes
docker compose exec manager python manage.py makemigrations

# Apply migrations
docker compose exec manager python manage.py migrate

# Check migration status
docker compose exec manager python manage.py showmigrations
```

### Testing

```bash
# Django unit tests
docker compose exec manager python manage.py test

# External acceptance tests
SUPASS=<password> make setup_tests
make -C tests manager-functional
```

### Running Locally

```bash
# Start with docker-compose
docker compose up -d manager

# View logs
docker compose logs manager -f

# Access Django shell
docker compose exec manager python manage.py shell

# Create superuser
docker compose exec manager python manage.py createsuperuser
```

## Key Configuration

### Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: Django secret key (from `manager/secrets/django/`)
- `DEBUG`: Enable debug mode (default: `False`)
- `ALLOWED_HOSTS`: Comma-separated allowed hostnames
- `SCENE_CONTROLLER_URL`: REST endpoint for Scene Controller
- `SUPASS`: Super user password (for initial setup)

### Configuration Files

- `requirements-runtime.txt`: Python dependencies
- `Dockerfile`: Container build instructions
- `config/settings.py`: Django settings
- `secrets/`: TLS certificates, database credentials, Django secret

### Secrets Management

```bash
# Initialize secrets (run once)
make init-secrets

# Regenerate secrets
make clean-secrets && make init-secrets
```

Secrets stored in `manager/secrets/`:

- `certs/`: TLS certificates (CA, server, client)
- `django/`: Django secret key
- `*.auth`: Service authentication tokens

## Code Patterns

### Creating a New Django View

```python
# In src/django/scenescape/views.py
from django.views.generic import ListView
from .models import Scene

class SceneListView(ListView):
    model = Scene
    template_name = 'scene_list.html'
    context_object_name = 'scenes'
```

### Adding REST API Endpoint

```python
# In src/django/api/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def scene_status(request, scene_id):
    # Query Scene Controller for runtime state
    controller_url = f"{settings.SCENE_CONTROLLER_URL}/scenes/{scene_id}/status"
    response = requests.get(controller_url, cert=client_cert, verify=ca_cert)
    return Response(response.json())
```

### Database Model

```python
# In src/django/scenescape/models.py
from django.db import models

class Camera(models.Model):
    camera_id = models.CharField(max_length=100, unique=True)
    scene = models.ForeignKey(Scene, on_delete=models.CASCADE)
    position_x = models.FloatField()
    position_y = models.FloatField()
    position_z = models.FloatField()
    calibrated = models.BooleanField(default=False)

    class Meta:
        db_table = 'cameras'
```

## Common Tasks

### Adding New Database Model

1. Define model in `src/django/scenescape/models.py`
2. Create migration: `docker compose exec manager python manage.py makemigrations`
3. Review migration file in `src/django/scenescape/migrations/`
4. Apply: `docker compose exec manager python manage.py migrate`
5. Update admin interface if needed: `src/django/scenescape/admin.py`

### Modifying Web UI

1. Edit template in `src/templates/`
2. Update static assets in `src/static/` (JS/CSS)
3. No rebuild needed—Django auto-reloads in development
4. For production, rebuild image to bundle assets

### Adding Management Command

```python
# Create src/management/commands/export_scenes.py
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Export scene data to JSON'

    def handle(self, *args, **options):
        # Implementation
        self.stdout.write(self.success('Export complete'))
```

Run with: `docker compose exec manager python manage.py export_scenes`

### Debugging Database Issues

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U scenescape -d scenescape

# List tables
\dt

# Describe table schema
\d cameras

# Check Django migrations
docker compose exec manager python manage.py showmigrations
```

## Integration Points

### Scene Controller

- Manager triggers operations via REST API
- Scene Controller maintains runtime state (object tracking)
- Manager stores persistent configuration (camera setup, scene definitions)

**Flow Example**: User creates scene in Manager → REST call to Scene Controller → Controller initializes runtime state → Manager saves metadata to DB

### Auto Calibration

- Manager UI triggers calibration requests
- Displays calibration status from Auto Calibration service
- Stores completed calibration parameters in database

### PostgreSQL

- All metadata persistence
- Schema managed by Django migrations
- Backup/restore via `pg_dump`/`pg_restore`

### Frontend Assets

- Static files served by Django (development) or Nginx (production)
- No separate frontend build process currently
- Future: Could integrate React/Vue build pipeline

## File Structure

```
manager/
├── Dockerfile                          # Container build
├── Makefile                            # Build rules
├── requirements-runtime.txt            # Python deps
├── src/
│   ├── django/                        # Django app
│   │   ├── scenescape/               # Main app
│   │   │   ├── models.py             # Database models
│   │   │   ├── views.py              # Web views
│   │   │   ├── urls.py               # URL routing
│   │   │   ├── admin.py              # Admin interface
│   │   │   └── migrations/           # DB migrations
│   │   └── api/                      # REST API
│   ├── management/                    # Management commands
│   ├── static/                        # Frontend assets
│   └── templates/                     # HTML templates
├── secrets/                           # Generated secrets (git-ignored)
│   ├── certs/                        # TLS certificates
│   └── django/                       # Django secret key
├── config/                            # Django settings
└── tools/                             # Utility scripts
```

## Troubleshooting

### Common Issues

1. **Database connection errors**
   - Verify PostgreSQL container is running: `docker compose ps postgres`
   - Check `DATABASE_URL` environment variable
   - Ensure database initialized: `docker compose exec postgres psql -U scenescape -c '\l'`

2. **Migration conflicts**
   - Check for pending migrations: `python manage.py showmigrations`
   - Resolve conflicts manually or fake migration: `python manage.py migrate --fake`
   - Worst case: Reset database (loses data)

3. **Static files not loading**
   - Run collectstatic: `docker compose exec manager python manage.py collectstatic`
   - Check `STATIC_ROOT` and `STATIC_URL` settings
   - Verify volume mounts in docker-compose.yml

4. **Authentication errors**
   - Check `SECRET_KEY` is set consistently across restarts
   - Verify user credentials in database
   - Clear sessions: `docker compose exec manager python manage.py clearsessions`

### Logs & Diagnostics

```bash
# Django logs
docker compose logs manager --tail 100

# Database logs
docker compose logs postgres --tail 100

# Django debug shell
docker compose exec manager python manage.py shell

# Check database connectivity
docker compose exec manager python manage.py dbshell
```

## Testing Checklist

When modifying the service, verify:

- [ ] Django unit tests pass: `docker compose exec manager python manage.py test`
- [ ] Database migrations apply cleanly
- [ ] REST API endpoints return correct responses
- [ ] Web UI pages render without errors
- [ ] Authentication/authorization works correctly
- [ ] Foreign key relationships maintained
- [ ] No SQL injection vulnerabilities (use ORM)
- [ ] CSRF protection enabled for forms

## Security Considerations

- **CSRF**: Django CSRF middleware enabled by default
- **SQL Injection**: Always use ORM queries, never raw SQL with user input
- **XSS**: Templates auto-escape by default
- **Authentication**: Use Django's built-in auth framework
- **TLS**: All external communication over HTTPS
- **Secrets**: Never commit secrets to git—use `secrets/` folder

## Performance Tips

- **Database Indexes**: Add indexes for frequently queried fields
- **Query Optimization**: Use `select_related()` and `prefetch_related()` to reduce queries
- **Caching**: Consider Redis for session storage and query caching
- **Static Files**: Use CDN or Nginx for production static file serving

## Related Documentation

- [Django Documentation](https://docs.djangoproject.com/): Official Django docs
- [Scene Controller API](../controller/docs/user-guide/api-docs/scene-controller-api.yaml): Backend API reference
- [Testing Guide](../.github/instructions/testing.md): Test creation patterns
- [Python Conventions](../.github/instructions/python.md): Python coding standards
