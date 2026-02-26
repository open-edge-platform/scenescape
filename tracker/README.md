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

The run targets are preconfigured to work with SceneScape demo. Start SceneScape first:

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

| Variable                   | Default                                      | Description                   |
| -------------------------- | -------------------------------------------- | ----------------------------- |
| `TRACKER_MQTT_HOST`        | `localhost`                                  | MQTT broker hostname          |
| `TRACKER_MQTT_PORT`        | `1883`                                       | MQTT broker port              |
| `TRACKER_MQTT_INSECURE`    | `false`                                      | Disable TLS (for test broker) |
| `TRACKER_MQTT_TLS_CA_CERT` | `../manager/secrets/certs/scenescape-ca.pem` | CA certificate path           |

Example with insecure test broker:

```bash
make run TRACKER_MQTT_INSECURE=true
```

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

# Run load tests (requires Docker and compose stack running)
make test-load
```

**Load Testing**

The tracker includes k6-based load testing to validate SLI performance under sustained load.

**What the test does:**

- Sends synthetic MQTT detection messages at configurable rates (default: 4 cameras × 15 FPS × 300 objects = 60 msg/s)
- Measures end-to-end latency (p50, p99) and per-stage latency breakdown
- Validates SLIs: dropped message rate < 0.1%, active track count, throughput

**Test parameters** are configurable via environment variables:

| Variable               | Default | Description                     |
| ---------------------- | ------- | ------------------------------- |
| `LOAD_TEST_DURATION_S` | `60`    | Duration of load test (seconds) |
| `LOAD_TEST_CAMERAS`    | `4`     | Number of simulated cameras     |
| `LOAD_TEST_FPS`        | `15`    | Frames per second per camera    |
| `LOAD_TEST_OBJECTS`    | `300`   | Max objects per frame           |

**Example: Run a 120-second test with 8 cameras at 30 FPS:**

```bash
make test-load LOAD_TEST_DURATION_S=120 LOAD_TEST_CAMERAS=8 LOAD_TEST_FPS=30
```

For full load test setup and troubleshooting, see [load test README](test/load/README.md).

### Docker

#### Prerequisites

Requires Docker runtime. Build dependencies are handled inside the container.

#### Images

Three image variants are available for different use cases:

| Image                               | Target    | Base Image                      | Use Case                        |
| ----------------------------------- | --------- | ------------------------------- | ------------------------------- |
| `scenescape-tracker`                | `runtime` | `gcr.io/distroless/cc-debian13` | Production deployment           |
| `scenescape-tracker-debug`          | `debug`   | `debian:13-slim`                | Remote debugging with gdbserver |
| `scenescape-tracker-relwithdebinfo` | `runtime` | `gcr.io/distroless/cc-debian13` | Profiling (optimized + symbols) |

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
