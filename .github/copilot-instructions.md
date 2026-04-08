# SceneScape AI Agent Instructions

Intel® SceneScape is a microservice-based spatial awareness framework for multimodal sensor fusion. This guide enables AI agents to work effectively in this distributed system.

**Current Version**: Read from `version.txt` at repository root

## Licensing Requirements (Critical - All Files)

**CRITICAL - All files must include:**

- SPDX license header: `SPDX-License-Identifier: Apache-2.0`
- Copyright line: `(C) <YEAR> Intel Corporation` (use current year for new files)
- Example:
  ```python
  # SPDX-FileCopyrightText: (C) 2026 Intel Corporation
  # SPDX-License-Identifier: Apache-2.0
  ```
- **Enforcement**: REUSE compliance checking in CI
- Add to new files: `make add-licensing FILE=<filename>`

## Language-Specific Skills (Load On-Demand)

Consult these based on the code you're working with:

- **Python** (`.github/skills/python.md`): Coding standards, imports, patterns
  - **CRITICAL**: 2 spaces for indentation (checked by `make indent-check`)
- **JavaScript** (`.github/skills/javascript.md`): Frontend conventions
- **Shell** (`.github/skills/shell.md`): Bash scripting guidelines
- **Makefile** (`.github/skills/makefile.md`): Build system conventions
- **Testing** (`.github/skills/testing.md`): Test creation frameworks

### Skills Caching Strategy

Skills are loaded on-demand based on task context to optimize token usage:

**Pre-Cached (Always Available)**:

- `copilot-instructions.md` (this file, always loaded)
- `python.md` (high frequency, pre-cached)
- `documentation-how.md` (high frequency, pre-cached)

**Loaded Automatically on Demand**:

- `testing.md` - Loaded when task involves tests or `test` keyword detected
- `javascript.md` - Loaded when `.js` files are being edited
- `shell.md` - Loaded when `.sh` files are being edited
- `makefile.md` - Loaded when Makefile or build system changes

Skills are detected and loaded based on file type, task keywords, and context signals. Explicitly request a skill if the auto-detection doesn't load it.

### Instruction Placement Policy (Critical)

- Prefer skill files under `.github/skills/` for detailed procedural rules.
- Keep this file focused on high-level routing and references to canonical skill documents.
- Avoid duplicating policy/checklist text across this file and skills.
- If overlap is found, retain one canonical source and replace duplicates with a short pointer.

## Architecture Overview

**Core Components:**

- **Scene Controller** (`controller/`): Central state management for scenes, objects, cameras via gRPC/REST
- **Manager** (`manager/`): Django-based web UI, REST API, PostgreSQL schema management
- **Auto Camera Calibration** (`autocalibration/`): Computes camera intrinsics/extrinsics from sensor feeds (docker-compose still references as `camcalibration`)
- **DL Streamer Pipeline Server**: Video analytics pipeline integration (external service config in `dlstreamer-pipeline-server/`)
- **Mapping & Cluster Analytics** (`mapping/`, `cluster_analytics/`): Experimental modules (enable via `build-experimental`)
- **Model Installer** (`model_installer/`): Manages OpenVINO Zoo model installation

**Message Flow:**

```
Sensors → MQTT (broker) → Scene Controller → Manager/Web UI
           ↓                              ↓
       JSON validation           PostgreSQL (metadata only)
```

**Key Insight**: Scene Controller maintains runtime state (object tracking, camera positions); Manager provides UI/persistence layer. No video/object location data persists in DB—only static configuration.

## Build System Patterns

**Multi-component Docker builds** organized in `common.mk`:

- Each service folder has `Makefile` + `Dockerfile` + `src/` + `requirements-*.txt`
- Parallel build: `JOBS=$(nproc)` (configurable via `make JOBS=4`)
- Shared base image: `scene_common` (required dependency for all services)
- Output: `build/` folder with logs and dependency lists

**Key Targets** (from root `Makefile`):

```bash
make build-core                    # Default: core services (autocalibration, controller, manager, model_installer)
make build-all                     # Includes experimental (mapping + cluster_analytics)
make build-experimental            # Mapping + cluster_analytics only
make rebuild-core                  # Clean + build (useful after code changes)
```

**Configuration** via environment/Makefile variables:

- `SUPASS`: Super user password (required for demos)
- `COMPOSE_PROJECT_NAME`: Container name prefix (default: `scenescape`)
- `BUILD_DIR`: Output folder for logs, dependency lists
- `CERTDOMAIN`: Certificate domain (default: `scenescape.intel.com`)

## Testing Framework

**For comprehensive test creation guidance, see `.github/skills/testing.md`** - detailed instructions on creating unit, functional, integration, UI, and smoke tests with both positive and negative cases.

**Running Tests** (must have containers running via docker-compose):

```bash
SUPASS=<password> make setup_tests                    # Build test images
make run_basic_acceptance_tests                       # Quick acceptance tests
make -C tests unit-tests                              # Unit tests only
make -C tests geometry-unit                           # Specific test (e.g., geometry)
```

### Completion Gate For Test Tasks (Critical)

For runtime test verification requirements, use
`.github/skills/test-verification-gate.md`.

### Containerized Test Image Freshness Gate (Critical)

Use `.github/skills/test-verification-gate.md` as the single source of truth
for image freshness checks, rebuild-before-test requirements, and retry policy
for containerized test targets.

Service-specific examples belong in each service guide (for controller, see
`controller/Agents.md`).

## Code Patterns & Conventions

**Python Packaging**:

- Each service: `setup.py` at root, source in `src/`, tests alongside
- Shared library: `scene_common/` installed as package dependency (geometry, MQTT, REST client, schema validation)
- Fast geometry: `fast_geometry/` C++ extension for spatial calculations

**MQTT/PubSub Pattern** (`scene_common.mqtt.PubSub`):

```python
pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)
pubsub.onMessage = handle_message  # Subscribe with callback
pubsub.publish(topic, json_payload)
```

**Data Validation**:

- Schema validation via `scene_common.schema.SchemaValidation` (JSON schema files in `controller/config/schema/`)
- Topics validate against schemas: `"singleton"`, `"detector"` (see `scene_controller.py` line 329-365)
- Detector messages: Camera ID in topic → validation against detector schema

**REST/gRPC Communication**:

- REST client: `scene_common.rest_client.RESTClient` (handles auth, certs, timeouts)
- Controller initialization: `SceneController.__init__` requires MQTT broker, REST URL, schema file, tracker config
- Configuration injection: Tracker behavior loaded from JSON config file (max unreliable time, frame rates)

**Observability** (Optional):

- Metrics/tracing: `controller.observability.metrics` module for OTEL instrumentation
- Environment variables: `CONTROLLER_ENABLE_METRICS`, `CONTROLLER_ENABLE_TRACING`, etc.
- Context manager: `metrics.time_mqtt_handler(attributes)` for latency tracking

## Common Developer Workflows

**Modifying a Microservice** (e.g., controller):

1. Edit source in `controller/src/`
2. Rebuild: `make rebuild-controller` (cleans old image, rebuilds)
3. Restart containers: `docker compose up -d scene` (or full `docker compose up`)
4. Check logs: `docker compose logs scene -f`

**Adding Dependencies**:

- Python: Update `requirements-runtime.txt`, rebuild image
- System: Add to `Dockerfile` RUN section (apt packages)
- Shared lib changes: Rebuild `scene_common`, then dependent services

**Debugging Tests**:

- Use `debugtest.py` for running tests without pytest harness (useful in containers)
- View test output: `docker compose exec <service> cat <logfile>`
- Specific test: `pytest tests/sscape_tests/geometry/test_point.py::TestPoint::test_constructor -v`

## Integration Points & Dependencies

**External Services** (docker-compose):

- NTP server: Time sync (required for tracking)
- PostgreSQL: Web UI metadata, scene/camera schemas
- Mosquitto MQTT: Message broker (TLS with certs from `manager/secrets/`)
- MediaMTX: RTSP media server for streaming (demo only)

**Model Installation**:

- `make install-models` → `model_installer/` service (OpenVINO Zoo models)
- Models volume: `scenescape_vol-models` (persistent across rebuilds)

**Secrets Management**:

- Generated by `make init-secrets` → `manager/secrets/certs/`, `manager/secrets/django`, `manager/secrets/*.auth`
- Required for TLS and service authentication (passed via docker-compose secrets)
- Can be regenerated with `make clean-secrets && make init-secrets`

**Kubernetes Deployment**:

- Helm chart: `kubernetes/scenescape-chart/`
- Reference: `kubernetes/README.md` for K8s-specific patterns
- Test via `make demo-k8s DEMO_K8S_MODE=core|all`

## File Organization Essentials

- **`Makefile`**: Root orchestrator; includes image build rules, test targets, clean targets
- **`docker-compose.yml`**: Service composition, networking, volume/secret management (generated from `docker-compose.template.yml` + env vars)
- **`.env`**: Runtime environment (database password, metrics config, COMPOSE_PROJECT_NAME)
- **`scene_common/src/scene_common/`**: Reusable modules (MQTT, REST, geometry, schema, logging)
- **`manager/secrets/`**: TLS certificates, auth tokens (never committed; generated per build)
- **`tests/Makefile`** and **`tests/Makefile.sscape`**: Test orchestration with Zephyr ID tracking

## Documentation Requirements (Always-On)

### WHEN to Update Documentation

**Update documentation IMMEDIATELY when making ANY of these changes:**

- Adding new features, services, models, or options
- Modifying APIs, endpoints, or request/response formats
- Changing build targets, Makefile commands, or deployment procedures
- Adding or removing configuration options or environment variables
- Updating dependencies or system requirements
- Changing default behaviors or conventions

### HOW to Update Documentation

**For detailed procedures, see `.github/skills/documentation-how.md`.**

This skill contains:

- Service-specific documentation locations (overview, build guides, API specs)
- Detailed update checklist per component
- Examples and patterns for each service type
- Cross-service documentation guidelines

**Quick reference - Key locations:**

- `docs/user-guide/microservices/<service>/<service>.md` - Features and API endpoints
- `docs/user-guide/microservices/<service>/get-started/build-from-source.md` - Build instructions
- `<service>/README.md` - Quick start
- `docs/user-guide/` - Cross-service documentation

## Quick Reference: New Service Checklist

When adding a new microservice:

1. Create folder with `Dockerfile`, `Makefile`, `src/`, `requirements-runtime.txt`
2. Source should import from `scene_common` for shared logic
3. Add `setup.py` if needed for local testing
4. Add docker-compose service (network: `scenescape`, depends_on appropriate services)
5. Update root `Makefile` `IMAGE_FOLDERS` and (optionally) `CORE_IMAGE_FOLDERS` or experimental groups
6. Create tests in `tests/sscape_tests/<service>/` with conftest.py fixtures
7. Add test-build target in service Makefile
8. **Update ALL relevant documentation** (overview, build guide, API docs, examples)
