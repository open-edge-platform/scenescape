# Tracker Service

High-performance C++ service for multi-object tracking with coordinate transformation and Kalman filtering.

## Overview

Transforms camera detections to world coordinates and maintains persistent object identities across frames and cameras. Built for real-time performance with horizontal scalability.

See [design document](../docs/design/tracker-service.md) for architecture details.

## Development

### Native

#### Prerequisites

```bash
# Install system dependencies (requires admin privileges)
sudo make install-deps

# Install build tools via pipx
make install-tools

# Coverage tools (optional, for local coverage reports)
pipx install gcovr
sudo apt-get install -y lcov

# MQTT client tools (optional, for manual testing)
sudo apt-get install -y mosquitto-clients
```

#### Build

```bash
# Release build (optimized)
make build

# Debug build
make build-debug

# Release with debug info (for profiling)
make build-relwithdebinfo
```

#### Run

The run targets are preconfigured to work with Scenescape demo. Start Scenescape first:

```bash
# From repository root
docker compose up -d
```

Then run the tracker:

```bash
# Run release build
make run

# Run debug build
make run-debug
```

**Environment overrides:** The following variables can be overridden:

| Variable                                 | Default                                      | Description                                      |
| ---------------------------------------- | -------------------------------------------- | ------------------------------------------------ |
| `TRACKER_MQTT_HOST`                      | `localhost`                                  | MQTT broker hostname                             |
| `TRACKER_MQTT_PORT`                      | `1883`                                       | MQTT broker port                                 |
| `TRACKER_MQTT_INSECURE`                  | `false`                                      | Disable TLS (for test broker)                    |
| `TRACKER_MQTT_TLS_CA_CERT`               | `../manager/secrets/certs/scenescape-ca.pem` | CA certificate path                              |
| `CONTROLLER_EXTERNAL_SOURCE_BINDINGS`    | Empty                                        | Comma-separated `publisher_id:scene_uid` entries |
| `CONTROLLER_TRUSTED_POSITIONING_SOURCES` | Empty                                        | Sources allowed to publish scene-frame poses     |

Example with insecure test broker:

```bash
make run TRACKER_MQTT_INSECURE=true
```

### External Sources

The tracker subscribes to `scenescape/external/{publisher_id}/{thing_type}` and
supports unified dynamic-source payloads containing `source_id`. The canonical
payload contract is documented in
[External Source Input Message Format](../docs/user-guide/microservices/controller/data_formats.md#external-source-input-message-format).

External object IDs are authoritative: they bypass RobotVision association and
are published unchanged, with cross-source collision protection. Camera and
external observations remain independent tracks and are not fused.

For image-map scenes, the tracker calculates the scene-local-to-ECEF transform at
startup from `map_corners_lla`, image dimensions, and the configured pixels-per-metre
`scale`, matching the Python Controller. API mode retrieves the map from the same
authenticated Manager origin; file mode reads the configured local map path. For
3D maps, the tracker uses Manager's generated PNG/JPEG top-view thumbnail and its
scale instead of downloading or parsing the GLB. A persisted `trs_matrix` remains
a final compatibility fallback when no usable image or thumbnail is available.
Scene-frame poses require an explicit binding and a source listed in
`CONTROLLER_TRUSTED_POSITIONING_SOURCES`.
Legacy configured child-scene payloads without `source_id` are not supported by
the C++ tracker.

**Manual execution:** If not using Make targets, you must source the Conan environment
first. Conan-managed libraries (e.g., OpenCV) are not installed system-wide, so
`LD_LIBRARY_PATH` must be set:

```bash
. build/conanrun.sh && ./build/tracker [args]
```

#### Test

```bash
# Run unit tests
make test-unit

# Run with coverage report (90% line, 50% branch)
make test-unit-coverage
# Report: build-debug/coverage/html/index.html

# Run camera-only load test (builds and manages its Compose stack)
make test-load

# Run external-only and combined load tests
make test-load-external
make test-load-mixed
```

**Load Testing**

The tracker includes k6-based camera-only, external-source-only, and mixed load tests.

**What the test does:**

- Sends synthetic MQTT detections at configurable camera and external-source rates
- Measures end-to-end latency (p50, p99) and per-stage latency breakdown
- Validates SLIs: dropped message rate < 0.1%, active track count, throughput

**Test parameters** are configurable via environment variables:

| Variable               | Default    | Description                     |
| ---------------------- | ---------- | ------------------------------- |
| `NUM_CAMERAS`          | `4`        | Simulated camera count          |
| `NUM_EXTERNAL_SOURCES` | `0` or `4` | External source count by target |
| `FPS`                  | `15`       | Messages per second per camera  |
| `EXTERNAL_FPS`         | `FPS`      | Messages per second per source  |
| `NUM_OBJECTS`          | `300`      | Objects per message/source      |
| `DURATION`             | `1m`       | Load duration                   |

**Example: Run a 5-minute mixed test with 8 cameras and 6 external sources:**

```bash
NUM_CAMERAS=8 NUM_EXTERNAL_SOURCES=6 FPS=30 EXTERNAL_FPS=20 DURATION=5m make test-load-mixed
```

For full load test setup and troubleshooting, see [load test README](test/load/README.md).

### Docker

#### Prerequisites

Requires Docker runtime. Build dependencies are handled inside the container.

#### Images

Three image variants are available for different use cases:

| Image                                     | Target    | Base Image                      | Use Case                        |
| ----------------------------------------- | --------- | ------------------------------- | ------------------------------- |
| `intel/scenescape-tracker`                | `runtime` | `gcr.io/distroless/cc-debian13` | Production deployment           |
| `intel/scenescape-tracker-debug`          | `debug`   | `debian:13-slim`                | Remote debugging with gdbserver |
| `intel/scenescape-tracker-relwithdebinfo` | `runtime` | `gcr.io/distroless/cc-debian13` | Profiling (optimized + symbols) |

#### Build

```bash
# Production image (minimal, distroless)
make build-image

# Debug image with gdbserver
make build-image-debug

# Release with debug info (for profiling)
make build-image-relwithdebinfo
```

#### Run

```bash
# Run production container
make run-image

# Run debug container (exposes gdbserver on port 2345)
make run-image-debug

# Stop debug container
make stop-image-debug
```

#### Test

```bash
# Service integration tests (requires built image)
make test-service
```

### Debugging

VSCode launch configurations are provided in `.vscode/launch.json` for debugging the tracker service. Open VSCode in the `tracker/` folder for these configurations to work.

Both debug configurations run `make clean` first to ensure you're debugging the latest code. This adds rebuild time but guarantees a fresh state.

#### Native Debugging

Debug a locally built binary:

1. Open VSCode and set breakpoints in source files
2. Run the **"Tracker: Debug native"** configuration (F5)

The preLaunchTask automatically:

1. Cleans previous build (`make clean`)
2. Builds the debug binary (`make build-debug`)
3. Generates `build-debug/debug.env` with library paths from `conanrun.sh`

#### Container Debugging (Remote GDB)

Debug the tracker running inside a Docker container using gdbserver:

1. Open VSCode and set breakpoints in source files
2. Run the **"Tracker: Debug container"** configuration

The preLaunchTask automatically:

1. Cleans previous build (`make clean`)
2. Builds the debug image (`make build-image-debug`)
3. Stops any existing debug container and starts a fresh one (`make run-image-debug`)

The debugger connects to `localhost:2345` and maps source files from `/scenescape/tracker` in the container to your local workspace.

When finished:

```bash
make stop-image-debug
```

### Profiling

Profile tracker with `perf` using the optimized RelWithDebInfo build:

```bash
# Record profile data (Ctrl+C to stop)
make profile

# Generate flamegraph visualization
make flamegraph
# Output: build-relwithdebinfo/flamegraph.svg
```

#### Perf Permissions

If you see "Error: Failure to open event", perf needs access to CPU performance counters.

**Temporary fix** (until reboot):

```bash
sudo sysctl kernel.perf_event_paranoid=-1
```

**Permanent fix**:

```bash
echo 'kernel.perf_event_paranoid=-1' | sudo tee /etc/sysctl.d/99-perf.conf
sudo sysctl -p /etc/sysctl.d/99-perf.conf
```

### Code Quality

```bash
make lint-all          # Run all linters
make lint-cpp          # C++ formatting check
make lint-dockerfile   # Dockerfile linting
make lint-python       # Python tests linting
make format-cpp        # Auto-format C++ code
make format-python     # Auto-format Python code
```

### Git Hooks

Install pre-commit hook to automatically check formatting:

```bash
make install-hooks
```

The hook runs `make lint-cpp`, `make lint-python`, and `make lint-dockerfile` in the tracker directory, and `make prettier-check` from the root scenescape directory before each commit to ensure code formatting compliance.

## Configuration

### Environment Variables

These settings are configured via the JSON config file or environment variables (not CLI flags):

| Variable           | Default | Description                 |
| ------------------ | ------- | --------------------------- |
| `LOG_LEVEL`        | `info`  | trace/debug/info/warn/error |
| `HEALTHCHECK_PORT` | `8080`  | Health endpoint HTTP port   |

### Command-Line Options

Run `tracker --help` for the full list of options:

```
tracker [OPTIONS] [SUBCOMMANDS]

OPTIONS:
  -h, --help                  Print this help message and exit
  -c, --config TEXT:FILE      Path to JSON configuration file
  -s, --schema TEXT:FILE      Path to JSON schema for configuration

SUBCOMMANDS:
  healthcheck                 Query service health endpoint
```

### Health Endpoints

```bash
# Liveness probe (process alive?)
curl http://localhost:8080/healthz
# {"status":"healthy"}

# Readiness probe (service ready?)
curl http://localhost:8080/readyz
# {"status":"ready"}
```

## Project Structure

```
tracker/
├── .vscode/          # VSCode debugging configurations
├── src/              # C++ source
│   ├── main.cpp                  # Entry point
│   ├── cli.cpp                   # CLI parsing (CLI11)
│   ├── config_loader.cpp         # JSON config loading
│   ├── logger.cpp                # Structured logging (quill)
│   ├── healthcheck_server.cpp    # HTTP server (httplib)
│   └── healthcheck_command.cpp   # Healthcheck CLI
├── inc/              # Headers
├── test/
│   ├── unit/         # GoogleTest + GMock
│   ├── service/      # pytest integration tests
│   └── load/         # pytest load tests + k6 generator
├── schema/           # JSON schemas
├── config/           # Default configuration
├── Dockerfile        # Multi-stage build
└── Makefile          # Build targets
```

## Dependencies

Managed via Conan 2.x. See [conanfile.txt](conanfile.txt) for the full list.

## CI/CD

GitHub Actions validates:

- C++ formatting (clang-format)
- Dockerfile linting (hadolint)
- Python formatting (autopep8)
- Security scan (Trivy, optional)
- Native build + unit tests
- Coverage enforcement (90% line, 50% branch)
- Docker build with cache
- Service integration tests

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for workflow.

## License

Apache-2.0
