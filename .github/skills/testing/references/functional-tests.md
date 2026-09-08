<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Functional and Integration Tests

**Location**: `tests/functional/` (integration-style flows also use this tree or `tests/system/`)

**Infrastructure**: `scenescape_env` in `tests/conftest.py` reads module-level `SCENESCAPE_SPEC`, starts the `ServiceProfile` stack, injects `params`, restores DB on teardown (unless `@pytest.mark.preserve_db`).

**Profiles**: `tests/utils/profiles.py`

**Real examples**: `tests/functional/test_roi_mqtt.py`, other modules under `tests/functional/`

## Required module header

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T10404"

@pytest.mark.basic_acceptance
@pytest.mark.test_name(TEST_NAME)
def test_roi_create(scenescape_env, demo_scene, request, result_recorder):
  # ... exercise MQTT/REST against live stack ...
  result_recorder.success()
```

## FuncTestSpec fields

Defined in `tests/utils/spec.py`:

| Field              | Purpose                                             |
| ------------------ | --------------------------------------------------- |
| `profile`          | `ServiceProfile` from `tests/utils/profiles.py`     |
| `auth`             | `AUTH_CONTROLLER` or `AUTH_BROWSER`                 |
| `require_password` | Default `True`                                      |
| `extra_args`       | Extra `--key value` pairs for params                |

Baseline scenes are selected per-profile via `_PROFILE_SCENE_ARCHIVES` in
`tests/conftest.py` (keys into `tests/utils/scene_baseline.SCENE_ARCHIVES`),
not via a `FuncTestSpec` field.

## Integration-style tests

Same `SCENESCAPE_SPEC` + live services pattern. Use when asserting cross-service flows (MQTT → controller → REST/DB). Prefer existing helpers (`SceneObjectMqtt`, `RESTClient`) over duplicating boilerplate.

## Multi-controller hierarchy fixtures

Use when a functional test needs **literal** remote children (separate Scene
Controller processes) on one host.

**Customer / deployment procedure** (unrelated: share or separate DBs; hierarchy:
shared with children, parent-only passthrough, or none):  
[ReID Across Controllers](../../../../docs/user-guide/how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md#reid-across-controllers-what-is-supported)

**Test harness pieces:**

| Piece | Role |
| ----- | ---- |
| `tests/compose/hierarchy/` | Prefixed parent/child1/child2 + VDMS fragments; unique host ports via env |
| `REID_HIER_*` in `tests/utils/profiles.py` | `REID_HIER_SHARED` / `REID_HIER_PARENT_ONLY` = supported happy paths (shared enroll+rematch; parent enrolls on no-match); `CHILDREN_ONLY` / `PARTIAL` / `SPLIT` = **unsupported-config guards** (assert no false merge / no double enroll) |
| `hierarchy_ports.py` + `scenescape_env.hierarchy_ports` | Allocate free host ports; sync `.env` **and** `os.environ` (process env wins over `--env-file`); clear on teardown |
| `hierarchy_env` in `tests/functional/conftest.py` | `params_parent` / `params_child1` / `params_child2` |
| `common_remote_child.RemoteHierarchySetup` | Create unique child scenes, remote links, wait for child status, parent regulated snapshots |
| `reid_backend.py` hostname/port overrides | Per-VDMS helpers for split-DB **negative** tests |
| `test_hierarchy_reid_db_scope.py` | Matrix NEX-T21928–21932 |
| `test_hierarchy_reid_enrollment.py` | Single-controller hierarchy enroll + no double-enroll; NEX-T21925 asserts `will_enroll` on child `DATA_EXTERNAL` after a confirmed write |

**Agent pitfalls:**

- Share one `SECRETSDIR`; broker/web/reid-s certs need SANs for hierarchy aliases
  (`BROKER_EXTRA_HOSTS` / `WEB_EXTRA_HOSTS` / `REID_S_EXTRA_HOSTS` via root
  `make certificates`).
- Children should NTP to the parent NTP service (`--rewriteBadTime` / maxlag help absorb residual skew in tests).
- Demo fixture UUID collides across child stacks—create a dedicated scene (+ camera) per child before linking.
- Prefer `@pytest.mark.preserve_db` for multi-controller matrices (each profile brings its own PG volumes).
- Hierarchy host ports are written to `os.environ` for Compose interpolation and
  cleared on stack teardown (`clear_hierarchy_port_env`).
- Controller product notes (remote `parent` recovery): `controller/Agents.md` hierarchy section.
