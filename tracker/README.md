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
make build-release

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
./build-release/tracker

# Custom log level
./build-release/tracker --log-level debug

# Healthcheck subcommand
./build-release/tracker healthcheck --endpoint /readyz

# Docker
make build-image
make run-image
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

```
tracker [OPTIONS] [SUBCOMMAND]

Options:
  -l, --log-level LEVEL      Log level (default: info)
  --healthcheck-port PORT    Health server port (default: 8080)
  -h, --help                 Show help

Subcommands:
  healthcheck                Query health endpoint
    --endpoint PATH          Endpoint path (default: /readyz)
```

## Dependencies

- **quill** 11.0.2 - Structured logging
- **CLI11** 2.6.0 - Argument parsing
- **httplib** 0.28.0 - HTTP server/client
- **rapidjson** - JSON serialization
- **simdjson** 4.2.2 - Fast JSON parsing
- **GoogleTest/GMock** 1.17.0 - Testing
- **RobotVision** - Kalman filtering (future)

Managed via Conan 2.x

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
