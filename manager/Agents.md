<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Manager Service - AI Agent Guide

## Documentation

- [MIGRATIONS.md](MIGRATIONS.md) - Django migrations workflow and best practices

## Service Overview

The **Manager** service is the Django-based web UI and REST API gateway for Scenescape. It provides user-facing interfaces for system configuration, scene management, camera setup, and PostgreSQL-backed persistence for metadata and configuration.

**Primary Purpose**: Web interface and REST API for managing Scenescape configuration, user authentication, and metadata persistence.

## Architecture & Components

### Core Modules

1. **Django Application** (`src/manager/`):
   - Scene management views and APIs
   - Camera configuration interfaces
   - User authentication and authorization
   - PostgreSQL ORM models

2. **REST API** (`src/manager/api.py`, `src/manager/serializers.py`, `src/manager/urls.py`):
   - RESTful endpoints for external integrations
   - Scene CRUD operations
   - Camera calibration triggers
   - Object query endpoints

3. **Management Commands** (`src/manager/management/commands/`):
   - Database migrations
   - Admin utilities
   - Data import/export tools

4. **Static Assets** (`src/manager/static/` and `src/static/`):
   - Frontend JavaScript/CSS
   - UI components
   - Visualization tools

5. **Templates** (`src/manager/templates/`):
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
- `/api/v1/calculateintrinsics/`: Calculate camera intrinsics
- `/api/v1/aclcheck/`: Validate broker topic ACLs
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
- `ENABLE_MLOPS_FLOW`: Enables the experimental MLOps Flow (ViPPET / DLSPS 2.0 pipeline integration; default
  off; Docker Compose only, deliberately not exposed in the Helm chart). Same as the
  `webserver --enable-mlops-flow` option, which wins over the variable.
  See [MLOps Flow feature flag](#mlops-flow-feature-flag)
- `VIPPET_URL`: ViPPET REST API root including `/api/v1` (e.g. `http://vippet:7860/api/v1`).
  Enables **Sync with ViPPET** on the Pipelines page. Passed through Docker Compose; empty
  disables the feature.
- `DLSPS_URL`: DL Streamer Pipeline Server 2.0 REST root (e.g. `http://dlsps:8080`). Enables
  starting/stopping camera pipelines. Passed through Docker Compose; empty disables the feature.
- `SUPASS`: Super user password (for initial setup)

### Configuration Files

- `requirements-runtime.txt`: Python dependencies
- `Dockerfile`: Container build instructions
- `src/manager/settings.py`: Django settings
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
# In src/manager/views.py
from django.views.generic import ListView
from .models import Scene

class SceneListView(ListView):
    model = Scene
    template_name = 'scene_list.html'
    context_object_name = 'scenes'
```

### Adding REST API Endpoint

```python
# In src/manager/api.py
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
# In src/manager/models.py
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

1. Define model in `src/manager/models.py`
2. Create migration: `docker compose exec manager python manage.py makemigrations`
3. Review migration file in `src/manager/migrations/`
4. Commit migration file to version control
5. Apply: `docker compose exec manager python manage.py migrate`
6. Update admin interface if needed: `src/manager/admin.py`

### Modifying Web UI

1. Edit template in `src/manager/templates/`
2. Update static assets in `src/manager/static/` (JS/CSS)
3. No rebuild needed—Django auto-reloads in development
4. For production, rebuild image to bundle assets

### Adding Management Command

```python
# Create src/manager/management/commands/export_scenes.py
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

- Manager UI triggers calibration requests through the web-proxied Auto Calibration service
- Autocalibration endpoints live under `/api/v1/autocalibration/` when accessed through the web container
- Stores completed calibration parameters in database

### ViPPET (Visual Pipeline and Platform Evaluation Tool)

- `manager.vippet.ViPPETClient` (`src/manager/vippet/`) pulls pipeline definitions authored in ViPPET:
  - `get_pipelines()` returns `PipelineSummary` objects (id, name, description, tags, variants with
    id and name) from `GET /pipelines`, without graphs or GStreamer strings
  - `get_pipeline_string(pipeline_id, variant_id)` returns the variant's GStreamer launch string
    (`GET /pipelines/{id}` + `POST /convert/to-description` with the variant's advanced graph)
- Only `vision` pipelines are exposed; `time_series` pipelines are hidden and reported as not found
- HTTP failures raise `ViPPETError` subclasses (`ViPPETUnavailableError` also covers ViPPET's 503
  while it initializes); invalid arguments or base URL raise `ValueError` before any request
- The returned string is persisted by value in `Pipeline.pipeline` and later submitted to DLSPS 2.0
  `POST /pipelines`; it still references ViPPET-side model/video paths
- Used by `manager.pipeline_runtime.sync_vippet_pipelines()` (Pipelines page **Sync with ViPPET**,
  `PipelineSyncView`, superuser + POST only): one `Pipeline` row per variant, named
  `"<pipeline name> (<variant name>)"`, matched on `vippet_pipeline_id = "<pipeline id>/<variant id>"`.
  Rows gone from ViPPET are kept; name clashes with other rows are skipped and reported
- Optional tag filter: `sync_vippet_pipelines(tag_filter)` takes a `TagFilter` built by
  `parse_tag_filter(text, match_all)` (comma-separated, case-insensitive whole-tag match, Any/All,
  max 20 tags of 100 chars). Non-matching ViPPET pipelines are skipped without fetching their
  strings, but variants already imported are still updated. `PipelineSyncForm` validates the input;
  `PipelineSyncView` stores the last filter in the session (`pipeline_sync_filter`) and the list
  view pre-fills it

### DL Streamer Pipeline Server 2.0

- `manager.dlsps.DLSPSClient` (`src/manager/dlsps/`) wraps the DLSPS 2.0 REST API: `create_pipeline`
  (`POST /pipelines` with a raw gst-launch string), `get_pipeline`, `get_pipeline_status`,
  `list_pipeline_statuses`, and `delete_pipeline`
- Responses are typed dataclasses (`PipelineStatus`, `PipelineSummary`); HTTP failures raise
  `DLSPSError` subclasses and invalid arguments raise `ValueError` before any request is sent
- Starting a pipeline is asynchronous: poll `get_pipeline_status` to detect `ERROR` after start
- Pipeline strings are executed as-is; use trusted server-side templates only because elements can
  access files and networks inside the DLSPS container, and restrict exposing APIs to administrators
- `manager.pipeline_runtime.reconcile_camera_pipeline()` runs after a camera is saved on the
  create, update and calibrate pages, and for the cameras of a pipeline whose string changed (UI
  edit or ViPPET sync). Under a `select_for_update` lock it compares the desired state (selected
  pipeline bound to the current `sensor_id`, sha256 in `Cam.dlsps_pipeline_digest`) with the
  recorded `Cam.dlsps_instance_id` and its live DLSPS status: a dead (ERROR/COMPLETED/ABORTED/404)
  instance is forgotten (ERROR is reported), a live one with another digest is stopped, and a
  missing one is started with `restart_config` enabled. Never decide from `form.changed_data`
- Stops are confirmed: `DELETE` only requests a stop and is rejected (409) for QUEUED instances,
  so `_stop_and_confirm` polls the status until it is terminal or 404, for up to
  `settings.DLSPS_STOP_TIMEOUT_S` (default 10). An unconfirmed stop keeps the recorded instance and
  starts nothing, so a camera never runs two instances. DLSPS itself reports ABORTED as soon as it
  accepts the stop and its worker exits about a second later, while a replacement validates for
  several seconds before processing frames. DLSPS failures never block the save; they are logged
  and shown as `messages` warnings
- A start without a usable answer (connection error/timeout, 5xx, invalid body) records
  `dlsps_start_uncertain` with the attempted digest instead of an instance id. The next reconcile
  adopts a live instance whose `launch_command` has that digest (`_find_live_instance`) and starts
  nothing while DLSPS cannot be listed. Only 4xx responses count as confirmed rejections
- `bind_pipeline_to_camera` tokenizes the launch string with quote awareness and only rewrites
  `sscape_post_inference_data_publish` element tokens, never text inside quoted values
- `Cam.RUNTIME_FIELDS` (`dlsps_instance_id`, `dlsps_pipeline_digest`, `dlsps_start_uncertain`) are
  written only by
  `pipeline_runtime` (`_set_runtime`, a queryset update). `Cam.save()` without `update_fields`
  skips them for existing rows, so a stale form or REST save cannot overwrite a newer handle
- A `pre_delete` signal on `Cam` (also fired for queryset and `Sensor` cascade deletes) re-reads
  the runtime fields under the row lock and writes a `PendingDLSPSStop` (instance id, or digest
  for an unconfirmed start) in the deletion transaction; the stop is attempted after commit and
  retried (bounded, `MAX_PENDING_STOP_ATTEMPTS`) by `retry_pending_stops()` at the start of every
  reconcile and sync. A REST update that changes `sensor_id` reconciles the camera
  (`CamSerializer.rebind_camera_pipeline`; warnings are only logged). Deleting a `Pipeline` does not call DLSPS. Instances are not
  recreated after a DLSPS restart until the camera is saved
- Camera pages show the live instance state via the `dlsps_instance_status` template tag
  (`templatetags/pipeline_tags.py`, 2 s timeout, `UNKNOWN` when DLSPS is unreachable)

### MLOps Flow feature flag

- `settings.ENABLE_MLOPS_FLOW` (from `ENABLE_MLOPS_FLOW`, or `--enable-mlops-flow` exported to
  Apache by `config/webserver-init`) gates the whole Pipelines feature; default off
- Off: `MlopsFlowSuperUserCheck` makes pipeline create/update/delete/sync views return 403 (the list
  stays readable); `CameraPipelineForm` marks `pipeline` as a disabled field, so posted values are
  ignored; `pipeline_runtime` entry points and the `Cam` `pre_delete` signal never call ViPPET or DLSPS
- Templates read `ENABLE_MLOPS_FLOW` and `MLOPS_FLOW_DISABLED_HINT` from the context processor and
  render greyed controls inside a `.mlops-flow-disabled` wrapper that carries the hint as `title`
- Tests that exercise the enabled feature use `@override_settings(ENABLE_MLOPS_FLOW=True)`
- MLOps Flow demo with an external ViPPET: `make demo-mlops-flow`
  (`sample_data/mlops_flow/README.md`)

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

- [ ] Functional tests pass: `make run_functional_tests` (starts Docker stacks automatically)
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
- [Scene Controller API](../docs/user-guide/microservices/controller/_assets/scene-controller-api.yaml): Backend API reference
- [Testing Guide](../.github/skills/testing/SKILL.md): Test creation patterns
- [Python Conventions](../.github/skills/python/SKILL.md): Python coding standards
