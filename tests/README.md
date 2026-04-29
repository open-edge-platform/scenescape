# Running tests for Intel® SceneScape on Docker

## Setup environment

```bash
# Build images, generate secrets, and install the pytest virtualenv
SUPASS=change_me make build-all && make setup-tests
make setup-pytest   # creates tests/.venv if not present
```

## Running tests

Tests are orchestrated by pytest. The `scenescape_env` fixture in
`tests/conftest.py` manages Docker Compose lifecycle (start, readiness polling,
container log collection, teardown). By default, container logs are collected
only for failed tests. Use `--collect-container-logs {failed,all,none}` to
change this behavior. Test specs are defined in the individual test
modules as Python dataclasses.

### Using make (recommended)

Use make targets from the repository root.

```bash
# One-time venv setup (auto-called by group targets)
make setup-pytest

# Run all basic acceptance tests
make run_basic_acceptance_tests

# Run standard tests (functional + UI)
make run_standard_tests

# Run all functional tests
make run_functional_tests

# Run all unit tests
make run_unit_tests

# Run all UI/Selenium tests
make run_ui_tests

```

### Using pytest directly

Run from the **repository root**:

```bash
# Activate the venv
source tests/.venv/bin/activate

# Run a single test by its pytest ID (use underscores)
pytest -k mqtt_roi -v

# Run multiple tests matching a keyword
pytest -k "mqtt" -v

# Run all functional tests
pytest tests/functional -v

# Run all unit tests
pytest tests/sscape_tests -v

# Run all UI tests
pytest tests/ui -v

# Container log collection modes (default: failed)
pytest tests/functional -v --collect-container-logs failed
pytest tests/functional -v --collect-container-logs all
pytest tests/functional -v --collect-container-logs none

```

### Environment variables

| Variable        | Default            | Description                                  |
| --------------- | ------------------ | -------------------------------------------- |
| `SUPASS`        | random             | Superuser password passed to test containers |
| `SECRETSDIR`    | `manager/secrets/` | Path to the secrets directory                |
| `IMAGE_VERSION` | `latest`           | Docker image tag to use for test containers  |

### Log files

Per-test log files are saved automatically:

```
tests/test_logs/functional/<test_id>-<timestamp>.log
tests/test_logs/unit/<test_id>-<timestamp>.log
tests/test_logs/ui/<test_id>-<timestamp>.log
```

Container log collection supports:

- `failed` (default): collect container logs only for failed tests.
- `all`: collect container logs for every test.
- `none`: skip container log collection entirely.

Console output is suppressed during teardown. Container-log and cleanup
messages are written to the per-test log file.

## Available test groups

| Make target              | Description                            |
| ------------------------ | -------------------------------------- |
| `run_basic_acceptance_tests` | Core smoke tests (functional + unit)   |
| `run_standard_tests`         | Full functional and UI test suite      |
| `run_functional_tests`       | All functional API/MQTT tests          |
| `run_unit_tests`             | All unit tests (standalone containers) |
| `run_ui_tests`               | All UI/Selenium tests                  |
| `run_metric_tests`           | Metric tests (Docker-based)            |

For a complete and up-to-date list of all test targets, see the root `Makefile`.

## Unit tests

Unit tests are run with:

```bash
make run_unit_tests
```

or directly with pytest:

```bash
pytest tests/sscape_tests -v
```

## Running tests on kubernetes

Refer to [Running tests on kubernetes](kubernetes/README.md)
