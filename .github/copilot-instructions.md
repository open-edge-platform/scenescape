# SceneScape AI Agent Instructions

Intel® SceneScape is a microservice-based spatial awareness framework for multimodal sensor fusion. This guide enables AI agents to work effectively in this distributed system.

**Current Version**: Read from `version.txt` at repository root

## Language-Specific Instructions

For detailed language-specific guidance, refer to `.github/instructions/<language>.md`:

- **Python**: `.github/instructions/python.md` - Python coding standards, patterns, and best practices
- **JavaScript**: `.github/instructions/javascript.md` - Frontend development conventions
- **Shell**: `.github/instructions/shell.md` - Bash scripting guidelines
- **Makefile**: `.github/instructions/makefile.md` - Build system conventions

Always consult the appropriate language-specific file when working with code in that language.

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

**For comprehensive test creation guidance, see `.github/instructions/testing.md`** - detailed instructions on creating unit, functional, integration, UI, and smoke tests with both positive and negative cases.

**Running Tests** (must have containers running via docker-compose):

```bash
SUPASS=<password> make setup_tests                    # Build test images
make run_basic_acceptance_tests                       # Quick acceptance tests
make -C tests unit-tests                              # Unit tests only
make -C tests geometry-unit                           # Specific test (e.g., geometry)
```

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

## Documentation Requirements

**ALWAYS read `.github/instructions/documentation.md` before making any code changes.** This file contains comprehensive documentation requirements and update procedures that must be followed for every agent request.

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

## Licensing Requirements

**All files must include:**

- SPDX license headers: `SPDX-License-Identifier: Apache-2.0`
- Copyright: Use current year `(C) <YEAR> Intel Corporation` (e.g., `(C) 2025 Intel Corporation` for files created in 2025)
- **Enforcement**: REUSE compliance checking in CI

**Add license to new files:**

```bash
make add-licensing FILE=<filename>
```
