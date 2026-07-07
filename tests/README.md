# Running tests for Scenescape

Tests support two deployment backends controlled by the `--backend` flag:

| Backend      | Description                         |
| ------------ | ----------------------------------- |
| `docker`     | Docker Compose (default)            |
| `kubernetes` | KinD cluster + Helm chart           |
| `all`        | Run each test against both backends |

## Prerequisites

### Host system packages

The following packages must be installed on the host before running `make setup-tests`.
Install them with `apt-get` (or equivalent for your distribution):

| Package         | Minimum version | Required for         | Install command                              |
| --------------- | --------------- | -------------------- | -------------------------------------------- |
| `firefox`       | 150.0.2         | UI / Selenium tests  | `sudo apt-get install -y firefox`            |
| `geckodriver`   | 0.36.0          | UI / Selenium tests  | Check https://github.com/mozilla/geckodriver |
| `xvfb`          | 21.1            | UI / Selenium tests  | `sudo apt-get install -y xvfb`               |
| `libopencv-dev` | 4.6             | `robot_vision` build | `sudo apt-get install -y libopencv-dev`      |
| `libeigen3-dev` | 3.4             | `robot_vision` build | `sudo apt-get install -y libeigen3-dev`      |

> **Note**: `firefox` and `xvfb` are only needed when running UI/Selenium tests.
> `libopencv-dev` and `libeigen3-dev` are required to compile the `robot_vision`
> C++ extension used by tracker metric and scene tests.
> On Ubuntu, Firefox must be installed via apt — the snap version is not compatible with Selenium.

### Docker backend

```bash
# Build images, generate secrets, and install the pytest virtualenv
SUPASS=change_me make && make setup-tests
```

### Kubernetes backend

In addition to the Docker prerequisites, the following tools must be installed
and available on `PATH`:

| Tool      | Purpose                        |
| --------- | ------------------------------ |
| `kind`    | Creates the local KinD cluster |
| `kubectl` | Manages Kubernetes resources   |
| `helm`    | Deploys the Scenescape chart   |

The Python dependencies are installed automatically by `make setup-pytest`.

The Kubernetes backend creates a fully self-contained KinD cluster, deploys
Scenescape via the Helm chart, and tears the cluster down at the end of the
test session.

## Running tests

Tests are orchestrated by pytest. The `scenescape_env` fixture in
`tests/conftest.py` manages Docker Compose lifecycle (start, readiness polling,
container log collection, teardown). By default, container logs are collected
only for failed tests. Use `--collect-container-logs {failed,all,none}` to
change this behavior. Test specs are defined in the individual test
modules as Python dataclasses.

### Running tests via make

Use make targets from the repository root.

```bash
# Run all basic acceptance tests
make run_basic_acceptance_tests

# Run standard tests (functional + UI)
make run_standard_tests

# Run all functional tests
make run_functional_tests

# Run all UI/Selenium tests
make run_ui_tests

# Run all unit tests
make run_unit_tests


```

### Running tests via pytest directly

Run from the **repository root**:

```bash
# Activate the venv
source tests/.venv/bin/activate

# ── Docker backend (default) ───────────────────────────────────────────────

# Run a single test by its pytest ID (use underscores)
pytest -k mqtt_roi

# Run all functional tests
pytest tests/functional

# Run all unit tests
pytest tests/sscape_tests

# Run all UI tests
pytest tests/ui

# ── Kubernetes backend ─────────────────────────────────────────────────────

# Run a specific test against Kubernetes
pytest tests/ui/test_out_of_box.py --backend=kubernetes

# Run all Kubernetes-capable tests
pytest --backend=kubernetes

# Run only tests that require Kubernetes
pytest -m kubernetes_only --backend=kubernetes

# Run all tests against both backends (parametrized)
pytest --backend=all

# ── Container log collection ───────────────────────────────────────────────
pytest tests/functional --collect-container-logs failed
pytest tests/functional --collect-container-logs all
pytest tests/functional --collect-container-logs none

```

### Environment variables

| Variable        | Default            | Backend | Description                                 |
| --------------- | ------------------ | ------- | ------------------------------------------- |
| `SUPASS`        | random             | both    | Superuser password for the test deployment  |
| `SECRETSDIR`    | `manager/secrets/` | docker  | Path to the secrets directory               |
| `IMAGE_VERSION` | `latest`           | docker  | Docker image tag to use for test containers |

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

| Make target                  | Description                            |
| ---------------------------- | -------------------------------------- |
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
pytest tests/sscape_tests
```

## Test markers

| Marker            | Description                                                                       |
| ----------------- | --------------------------------------------------------------------------------- |
| `kubernetes_only` | Test runs only with `--backend=kubernetes` or `--backend=all`; skipped for Docker |
| `preserve_db`     | Skip post-test DB restore so the next test can verify persistence                 |

## Using the VS Code Test Extension

The workspace is pre-configured for the **Python Testing** extension
(`ms-python.python`). Tests are discovered automatically from the `tests/`
directory.

### Docker backend (default)

No extra configuration is needed. Open the **Testing** sidebar, click
**Run All Tests** or select individual tests.

### Kubernetes backend

To run tests against the Kubernetes backend from the Test Explorer, add
`--backend=kubernetes` to the pytest args in your VS Code workspace settings:

1. Open `.vscode/settings.json` (repository root).
2. Add `--backend=kubernetes` to `python.testing.pytestArgs`:

   ```json
   {
     "python.testing.pytestArgs": ["tests", "--backend=kubernetes"],
     "python.testing.pytestEnabled": true,
     "python.testing.unittestEnabled": false
   }
   ```

3. Click **Refresh Tests** in the Testing sidebar, then run as normal.

### Running both backends

Set `--backend=all` to parametrize every test across Docker and Kubernetes in
a single session. Each test appears in the Test Explorer as
`test_name[docker]` and `test_name[kubernetes]`.
