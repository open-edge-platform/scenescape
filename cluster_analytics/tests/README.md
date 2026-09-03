<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Cluster Analytics Tests

Two test tiers are provided: **unit tests** (fast, no Docker) and **component tests**
(real MQTT pipeline, requires Docker).

## Unit Tests

Located in `tests/sscape_tests/cluster_analytics/` (repo-level test tree).

Test what each function/class does in isolation:

| File                 | What it covers                                                       |
| -------------------- | -------------------------------------------------------------------- |
| `test_config.py`     | Config loading, defaults, per-category DBSCAN overrides              |
| `test_clustering.py` | DBSCAN grouping, centroids, noise exclusion, empty inputs            |
| `test_shape.py`      | Shape detection: circle, line, irregular, insufficient points        |
| `test_velocity.py`   | Velocity classification: stationary, parallel, converging, diverging |
| `test_tracker.py`    | Tracker UUID persistence, nearest-centroid matching, expiry          |

### Setup

1. **Create and activate a Python virtual environment** (from repo root):

   ```bash
   python3.14 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install the required packages** (from `tests/` folder):

   ```bash
   cd tests/
   pip install -r requirements.txt
   ```

### Run from repo root:

```bash
python -m pytest tests/sscape_tests/cluster_analytics/ -v -p no:django
```

`-p no:django` is required because the repo-level `pytest.ini` loads Django; the
cluster analytics tests do not need it and `manager/secrets/` may not be present.

Expected result: **41 passed**.

---

## Component Tests

Located in `cluster_analytics/tests/service/`.

Spin up a real Mosquitto broker + cluster-analytics container, inject DATA_REGULATED
messages over MQTT, and assert on the ANALYTICS_CLUSTERS output.

### Prerequisites

1. **Python virtual environment activated** (from repo root):

   ```bash
   python3.14 -m venv .venv
   source .venv/bin/activate
   ```

2. **Docker** available on the host.

3. **Test image built:**

   ```bash
   # From cluster_analytics/
   make test-build
   ```

   This requires `scenescape-common-base:latest` to exist. If it does not:

   ```bash
   # From repo root — builds scene_common and tags it :latest
   make build-common
   make -C cluster_analytics test-build
   ```

4. **Test dependencies installed** (paho-mqtt, python-on-whales, etc.):

   ```bash
   cd tests/
   pip install -r requirements.txt
   ```

### Run

```bash
# From repo root
pytest cluster_analytics/tests/service/ -v
```

Each test gets its own isolated compose stack (unique project name) so tests can
run safely in sequence. The fixture waits for `"Subscribed to"` in the container
logs before proceeding.

### Tracker warmup

The centroid tracker publishes clusters from the **first frame** — there is no
state-machine warmup. `_warmup_and_publish()` sends **one** silent priming frame
to establish the cluster UUID in tracker state, then publishes the assertion frame
whose response is returned.

Tests that expect empty results (0 objects, 1 object below `min_samples`) do not
need warmup because they never produce clusters.

Expected result: **7 passed**.

---

## Test Hierarchy Summary

```
Unit tests        — tests/sscape_tests/cluster_analytics/   (no Docker, 41)
Component tests   — cluster_analytics/tests/service/         (Docker, 7)
E2E functional    — tests/functional/                        (full stack, not yet implemented)
```
