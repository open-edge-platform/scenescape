# Tracker Service AI Agent Instructions

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (C) 2026 Intel Corporation -->

## Service Overview

The Tracker Service is a high-performance C++ microservice that aggregates detection messages from cameras using time-chunked processing and publishes tracked object data to scene topics. It uses Kalman filtering via RobotVision library for temporal consistency.

**Key Difference**: Unlike other SceneScape services (Python), the Tracker Service is implemented in C++ with Conan 2.x dependency management, CMake + Ninja builds, and distroless production images.

## Architecture Overview

The service uses a multi-threaded pipeline: `MqttClient` receives detections → `TimeChunkBuffer` aggregates by time window → `TrackingManager` runs per-scope tracking workers → `TrackPublisher` emits tracked objects. Time-chunk processing aggregates detections into fixed intervals (default 66.7ms / 15 FPS) before tracking.

**For detailed architecture, see**: [docs/design/tracker-service/](../docs/design/tracker-service/)

**Related ADRs**: ADR-0003 (C++ Implementation), ADR-0007 (Time Chunking), ADR-0008 (Horizontal Scaling)

## Build System

Uses dedicated Makefile with Conan 2.x + CMake + Ninja. All builds run inside Docker containers for reproducibility.

### Key Makefile Targets

| Target                    | Description                        |
| ------------------------- | ---------------------------------- |
| `make build`              | Release build                      |
| `make build-debug`        | Debug build with test binaries     |
| `make build-image`        | Production distroless Docker image |
| `make build-image-debug`  | Debug image with gdbserver         |
| `make test-unit`          | Run unit tests                     |
| `make test-unit-coverage` | Coverage with enforced thresholds  |
| `make test-service`       | pytest integration tests           |
| `make lint-all`           | C++, Python, Dockerfile linting    |
| `make profile`            | perf profiling                     |
| `make flamegraph`         | Generate flamegraph visualization  |

## Schema Validation

All configuration and message formats have JSON schemas in `tracker/schema/`:

| Schema                   | Purpose                          |
| ------------------------ | -------------------------------- |
| `config.schema.json`     | Service configuration validation |
| `scenes.schema.json`     | Scene definition validation      |
| `detection.schema.json`  | Input detection message format   |
| `scene-data.schema.json` | Output track message format      |
| `log.schema.json`        | Structured logging format        |

**CRITICAL**: All config and message format changes MUST validate against schemas. Schema modifications require updating BOTH the schema file AND design documentation in `docs/design/tracker-service/`.

## Environment Variable Overrides

**CRITICAL**: Any new config option MUST have a corresponding environment variable override. There is no library handling this automatically—manual implementation in `src/config_loader.cpp` is required.

| Variable                         | Description                            |
| -------------------------------- | -------------------------------------- |
| `TRACKER_LOG_LEVEL`              | trace/debug/info/warn/error            |
| `TRACKER_HEALTHCHECK_PORT`       | HTTP health endpoint port (1024-65535) |
| `TRACKER_MQTT_HOST`              | MQTT broker hostname                   |
| `TRACKER_MQTT_PORT`              | MQTT broker port                       |
| `TRACKER_MQTT_INSECURE`          | Disable TLS (true/false)               |
| `TRACKER_MQTT_TLS_CA_CERT`       | CA certificate path                    |
| `TRACKER_MQTT_TLS_CLIENT_CERT`   | Client certificate path                |
| `TRACKER_MQTT_TLS_CLIENT_KEY`    | Client key path                        |
| `TRACKER_MQTT_TLS_VERIFY_SERVER` | Server cert verification               |
| `TRACKER_MQTT_SCHEMA_VALIDATION` | Enable/disable schema validation       |
| `TRACKER_MAX_LAG_S`              | Max detection frame lag                |
| `TRACKER_TIME_CHUNKING_RATE_FPS` | Processing rate (1-60 FPS)             |
| `TRACKER_MAX_WORKERS`            | Worker thread limit                    |
| `TRACKER_SCENES_SOURCE`          | "file" or "api"                        |
| `TRACKER_SCENES_FILE_PATH`       | Scenes JSON path (file mode)           |

### Adding New Config Options

1. Add field to `config/config.schema.json`
2. Add default in `config/tracker.json`
3. Add env var parsing in `src/config_loader.cpp` `applyEnvironmentOverrides()`
4. Update this table and design docs

## Coverage Requirements (Enforced)

The Tracker Service enforces strict test coverage thresholds via CI:

- **Line coverage**: ≥ 90%
- **Branch coverage**: ≥ 50%

Run `make test-unit-coverage` to verify locally. New code MUST maintain these thresholds or CI will fail.

## MQTT Topics

**Subscribes**: `scenescape/data/camera/+` — Detection messages from cameras

**Publishes**: `scenescape/data/scene/<scene_id>` — Tracked object messages

## Development Workflows

### Building and Testing

```bash
cd tracker
make build                    # Release build
make test-unit                # Run unit tests
make test-unit-coverage       # Verify coverage thresholds
make test-service             # Integration tests (requires running services)
make lint-all                 # All linting checks
```

### Running Locally

```bash
make run              # Run tracker binary directly
make run-image        # Run tracker in container
```

### Debugging

VSCode configurations exist in `.vscode/` for:

- Native debugging (local builds)
- Remote debugging via gdbserver (container builds)

Use `make build-image-debug` for debuggable container images.

## File Structure

```
tracker/
├── Makefile              # Build orchestration (Conan + CMake)
├── CMakeLists.txt        # CMake configuration
├── conanfile.txt         # C++ dependencies
├── config/
│   ├── tracker.json      # Default service config
│   └── scenes.json       # Example scene definitions
├── schema/               # JSON schemas for validation
├── src/                  # C++ source files
│   ├── main.cpp          # Entry point, signal handling
│   ├── cli.cpp           # CLI argument parsing
│   ├── config_loader.cpp # Config + env var loading
│   ├── mqtt_client.cpp   # MQTT integration
│   ├── time_chunk_*.cpp  # Time-chunk processing
│   ├── tracking_*.cpp    # Tracking logic
│   └── healthcheck_*.cpp # HTTP health endpoints
├── include/              # C++ headers
└── tests/                # pytest integration tests
```

## Common Tasks

### Adding New MQTT Message Types

1. Create/update schema in `schema/`
2. Update message handling in `src/mqtt_dispatcher.cpp`
3. Add unit tests maintaining coverage thresholds
4. Update design docs in `docs/design/tracker-service/`

### Performance Analysis

```bash
make profile       # Run perf profiling
make flamegraph    # Generate flamegraph (requires perf data)
```

## Testing Checklist

Before submitting changes:

- [ ] `make lint-all` passes
- [ ] `make test-unit-coverage` meets thresholds (90% line, 50% branch)
- [ ] `make test-service` passes (if MQTT changes)
- [ ] Schema changes validated and documented
- [ ] Environment variable overrides added for new config options
- [ ] Design docs updated if architecture/behavior changes

## Related Documentation

- [Tracker Service Design](../docs/design/tracker-service/design.md)
- [Implementation Guide](../docs/design/tracker-service/implementation.md)
- [Controller Agents.md](../controller/Agents.md) — Scene Controller integration
- [ADR-0003](../docs/adr/0003-tracker-cpp.md) — C++ Implementation Decision
- [ADR-0007](../docs/adr/0007-time-chunking.md) — Time Chunking Design
- [ADR-0008](../docs/adr/0008-horizontal-scaling.md) — Horizontal Scaling Strategy
