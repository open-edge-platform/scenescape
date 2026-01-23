# Tracker Service

High-performance C++ service for multi-object tracking with coordinate transformation and Kalman filtering.

## Overview

Transforms camera detections to world coordinates and maintains persistent object identities across frames and cameras. Built for real-time performance with horizontal scalability.

See [design document](../docs/design/tracker-service.md) for architecture details.

## Quick Start

### Prerequisites

```bash
# Install system dependencies (requires admin privileges)
sudo make install-deps

# Install build tools via pipx
make install-tools

# Additional CI tools (optional)
pip install gcovr
sudo apt-get install -y lcov
```

### Build

```bash
# Release build (optimized)
make build

# Debug build with tests
make build-debug

# Run unit tests
make test-unit

# Run with coverage report
make test-unit-coverage
```

### Run

```bash
# Run with default settings
make run

# Debug build
make run-debug

# Docker
make build-image
make run-image
```

**Manual execution:** If not using Make targets, you must source the Conan environment
first. Conan-managed libraries (e.g., OpenCV) are not installed system-wide, so
`LD_LIBRARY_PATH` must be set:

```bash
. build/conanrun.sh && ./build/tracker [args]
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

## Development

### Testing

```bash
make test-unit              # Run unit tests
make test-unit-coverage     # Generate coverage (60% line, 30% branch)
make test-service           # Docker service tests
```

Coverage report: `build-debug/coverage/html/index.html`

### Code Quality

```bash
make lint-all          # Run all linters
make lint-cpp          # C++ formatting check
make lint-dockerfile   # Dockerfile linting
make lint-python       # Python tests linting
make format-cpp        # Auto-format C++ code
```

### Git Hooks

Install pre-commit hook to automatically check formatting:

```bash
make install-hooks
```

The hook runs `make lint-cpp` and `make lint-python` before each commit to ensure code formatting compliance.

### Project Structure

```
tracker/
├── src/              # C++ source
│   ├── main.cpp                  # Entry point
│   ├── cli.cpp                   # CLI parsing (CLI11)
│   ├── logger.cpp                # Structured logging (quill)
│   ├── healthcheck.cpp           # HTTP server (httplib)
│   └── healthcheck_command.cpp   # Healthcheck CLI
├── inc/              # Headers
├── test/
│   ├── unit/         # GoogleTest + GMock
│   └── service/      # pytest integration tests
├── schemas/          # JSON schemas
├── Dockerfile        # Multi-stage build
└── Makefile          # Build targets
```

## Configuration

### Environment Variables

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
  -l, --log-level TEXT        Log level (trace|debug|info|warn|error)
                              Default: info, Env: LOG_LEVEL
      --healthcheck-port INT  Healthcheck server port (1024-65535)
                              Default: 8080, Env: HEALTHCHECK_PORT

SUBCOMMANDS:
  healthcheck                 Query service health endpoint
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
- Coverage enforcement (60% line, 30% branch)
- Docker build with cache
- Service integration tests

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for workflow.

## License

Apache-2.0
