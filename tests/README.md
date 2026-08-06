# Running tests for Scenescape

Tests support two deployment backends controlled by the `--backend` flag:

| Backend      | Description                         |
| ------------ | ----------------------------------- |
| `docker`     | Docker Compose (default)            |
| `kubernetes` | KinD cluster + Helm chart           |
| `all`        | Run each test against both backends |

## Prerequisites

### Host system packages

Install all required packages:

```bash
sudo apt-get update && sudo apt-get install -y \
  build-essential \
  python3.12-dev \
  python3.12-venv \
  xvfb \
  libopencv-dev \
  libeigen3-dev
```

**Note:** Firefox must be set up separately (see [Firefox Setup](#firefox-setup) below).

### Firefox Setup

Firefox **must** be installed as a real binary (not snap), as snap Firefox is incompatible with Selenium.

**Manual setup**

For Ubuntu 24.04+:

```bash
sudo add-apt-repository -y ppa:mozillateam/ppa
sudo apt-get update && sudo apt-get install -y firefox-esr
sudo ln -sf /usr/bin/firefox-esr /usr/bin/firefox
```

Verify Firefox is installed correctly:

```bash
firefox --version  # Should show Mozilla Firefox (not snap)
```

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

| Variable          | Default                   | Backend  | Description                                 |
| ----------------- | ------------------------- | -------- | ------------------------------------------- |
| `SUPASS`          | random                    | both     | Superuser password for the test deployment  |
| `SECRETSDIR`      | `manager/secrets/`        | docker   | Path to the secrets directory               |
| `IMAGE_VERSION`   | `latest`                  | docker   | Docker image tag to use for test containers |
| `FIREFOX_BIN`     | `firefox` (from PATH)     | UI tests | Path to Firefox binary for Selenium tests   |
| `GECKODRIVER_BIN` | `geckodriver` (from PATH) | UI tests | Path to geckodriver binary for Selenium     |

### Log files

Per-test log files are saved automatically:

```
tests/.test_logs/<group>/<test_id>/<test_id>-<timestamp>.log
```

Log content depends on the test outcome:

- **Passing test** — only the raw `print()` output from the test body plus any log records are kept.
- **Failing test** — the full orchestration log is preserved for
  debugging, along with per-container Docker logs in a sibling
  directory (unless `--collect-container-logs=none` is set):

  ```
  tests/.test_logs/<group>/<test_id>/<test_id>-<timestamp>-containers/<service>.log
  ```

Container log collection modes (`--collect-container-logs`):

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

## Multi-controller hierarchy (functional)

Literal parent + child Scene Controllers on one host use Compose fragments under
`tests/compose/hierarchy/` and `REID_HIER_*` profiles. Agent-oriented fixture
notes: [multi-controller hierarchy fixtures](../.github/skills/testing/references/functional-tests.md#multi-controller-hierarchy-fixtures).
Deployment guide: [Deploy Multiple Controllers on One Host](../docs/user-guide/how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md).

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
