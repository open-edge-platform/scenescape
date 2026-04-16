# Running tests for Intel® SceneScape on Docker

## Setup environment

```bash
# Build images, generate secrets, and install the pytest virtualenv
SUPASS=change_me make build-all && make setup_tests
cd tests && make setup-pytest   # creates tests/.venv if not present
```

## Running tests

Tests are orchestrated by pytest. The `scenescape_env` fixture in
`tests/conftest.py` manages Docker Compose lifecycle (start, readiness polling,
log collection, teardown). All test specs are defined as Python dataclasses in
`tests/test_functional.py`, `tests/test_unit.py`, and `tests/test_ui.py`.

### Using make (recommended)

Each `make -C tests <target>` invokes `tests/.venv/bin/pytest -k <test_id>`.

```bash
# One-time venv setup (auto-called by group targets)
make -C tests setup-pytest

# Run all basic acceptance tests
make -C tests basic-acceptance-tests

# Run standard tests (functional + UI)
make -C tests standard-tests

# Run all functional tests
make -C tests functional-tests

# Run all unit tests
make -C tests unit-tests

# Run all UI/Selenium tests
make -C tests ui-tests

# Run a specific test by its make target name
make -C tests mqtt-roi
make -C tests geometry-unit
make -C tests bounding-box

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
pytest tests/test_functional.py -v

# Run all unit tests
pytest tests/test_unit.py -v

# Run all UI tests
pytest tests/test_ui.py -v

```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `SUPASS` | random | Superuser password passed to test containers |
| `SECRETSDIR` | `manager/secrets/` | Path to the secrets directory |
| `IMAGE_VERSION` | `latest` | Docker image tag to use for test containers |

### Log files

Per-test log files are saved automatically:

```
tests/test_logs/functional/<test_id>-<timestamp>.log
tests/test_logs/unit/<test_id>-<timestamp>.log
tests/test_logs/ui/<test_id>-<timestamp>.log
```

Console output is suppressed during teardown — container log collection and
cleanup messages go to the log file only.

## Available test groups

| Make target | Description |
|---|---|
| `basic-acceptance-tests` | Core smoke tests (functional + unit) |
| `standard-tests` | Full functional and UI test suite |
| `functional-tests` | All functional API/MQTT tests |
| `unit-tests` | All unit tests (standalone containers) |
| `ui-tests` | All UI/Selenium tests |
| `metric-tests` | Performance metric tests |

For a complete and up-to-date list of all test targets see the
[Tests Makefile](Makefile), [Makefile.functional](Makefile.functional),
[Makefile.sscape](Makefile.sscape), and [Makefile.user_interface](Makefile.user_interface).

## Unit test taxonomy

The repository keeps two categories under the `unit-tests` umbrella:

- Pure unit tests: fast logic-focused tests that typically avoid Django request/ORM integration.
  - Umbrella target: `make -C tests logic-unit-tests`
  - Example leaf target: `make -C tests scene-unit`
- Django integration unit tests: Django `TestCase`/test-client/ORM based backend tests grouped under a dedicated umbrella.
  - Umbrella target: `make -C tests django-integration-unit`
  - Included targets: `account-security-unit`, `cam-unit`, `scene-django-unit`, `singleton-sensor-unit`, `views-unit`

Notes:

- `make -C tests unit-tests` still runs both categories.
- The Django scene CRUD tests in `tests/sscape_tests/scene/` are run by `scene-django-unit`.

## Running tests on kubernetes

Refer to [Running tests on kubernetes](kubernetes/README.md)
