# Tracker Service AI Agent Instructions

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (C) 2026 Intel Corporation -->

## Service Overview

The Tracker Service is a high-performance C++ microservice that aggregates detection messages from cameras using time-chunked processing and publishes tracked object data to scene topics. It uses Kalman filtering via RobotVision library for temporal consistency.

**Key Difference**: Unlike other SceneScape services (Python), the Tracker Service is implemented in C++ with Conan 2.x dependency management, CMake + Ninja builds, and distroless production images.

## Architecture Overview

The service uses a multi-threaded pipeline: `MqttClient` receives detections → `TimeChunkBuffer` aggregates by time window → `TrackingManager` runs per-scope tracking workers → `TrackPublisher` emits tracked objects. Time-chunk processing aggregates detections into fixed intervals (default 66.7ms / 15 FPS) before tracking.

**For detailed architecture, see**: [Design Document](../docs/design/tracker-service.md) | [Implementation Guide](docs/implementation.md)

**Related ADRs**: [ADR-0003](../docs/adr/0003-scaling-controller-performance.md) (C++ Implementation), [ADR-0007](../docs/adr/0007-tracker-service.md) (Time Chunking), [ADR-0008](../docs/adr/0008-tracker-service-horizontal-scaling.md) (Horizontal Scaling)

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
| `make test-load`          | k6 load test + drop-rate assertion |
| `make lint-all`           | C++, Python, Dockerfile linting    |
| `make profile`            | perf profiling                     |
| `make flamegraph`         | Generate flamegraph visualization  |

## Schema Validation

All configuration and message formats have JSON schemas in `schema/` — inspect that directory for current schemas.

**CRITICAL**: All config and message format changes MUST validate against schemas. Schema modifications require updating BOTH the schema file AND design documentation in `docs/`.

## Environment Variable Overrides

**CRITICAL**: Any new config option MUST have a corresponding environment variable override. There is no library handling this automatically — manual implementation in `src/config_loader.cpp` is required.

All `TRACKER_*` environment variables are defined in `inc/env_vars.hpp` — inspect that file for the current list. The config schema (`schema/config.schema.json`) documents valid values and ranges.

### Adding New Config Options

1. Add field to `schema/config.schema.json`
2. Add default in `config/tracker.json` and `TrackingConfig` struct in `inc/config_loader.hpp`
3. Add env var constant in `inc/env_vars.hpp`
4. Add env var parsing in `src/config_loader.cpp`
5. Update design docs

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
make test-load                # k6 load test + drop-rate assertion
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
├── Makefile          # Build orchestration (Conan + CMake)
├── CMakeLists.txt    # CMake configuration
├── config/           # Default config files
├── schema/           # JSON schemas for validation
├── src/              # C++ source files
├── inc/              # C++ headers
└── test/             # Unit tests and integration tests
```

Key entry points: `src/main.cpp` (service startup), `src/config_loader.cpp` (config + env vars), `inc/env_vars.hpp` (environment variable definitions).

## Common Tasks

### Adding New MQTT Message Types

1. Create/update schema in `schema/`
2. Update message handling in `src/mqtt_dispatcher.cpp`
3. Add unit tests maintaining coverage thresholds
4. Update design docs in `docs/`

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
- [ ] `make test-load` passes (if metrics/performance changes — drops < 0.1%)
- [ ] Schema changes validated and documented
- [ ] Environment variable overrides added for new config options
- [ ] Design docs updated if architecture/behavior changes

## Related Documentation

- [Tracker Service Design](../docs/design/tracker-service.md) — High-level design document
- [Implementation Guide](docs/implementation.md)
- [Controller Agents.md](../controller/Agents.md) — Scene Controller integration
- [ADR-0003](../docs/adr/0003-scaling-controller-performance.md) — C++ Implementation Decision
- [ADR-0007](../docs/adr/0007-tracker-service.md) — Tracker Service Design
- [ADR-0008](../docs/adr/0008-tracker-service-horizontal-scaling.md) — Horizontal Scaling Strategy
