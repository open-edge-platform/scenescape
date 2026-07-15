# Analytics Refactor Plan: Decouple from Controller

## Context

The analytics package currently lives at `controller/src/controller/analytics/` — inside the controller package namespace. This creates backwards coupling: the analytics service imports from controller, and the controller imports analytics code inline for event processing.

**Root cause:** Wrong location at Phase 2 implementation. The design (phases 1–6 in `analytics_plan.md`) was correct; the package location was wrong from day one.

**Goal:** Move analytics to a standalone package, strip inline analytics from controller, and move shared infrastructure to `scene_common`.

---

## Phases Overview

| Phase | Goal | Effort | Unblocks |
|-------|------|--------|----------|
| 1 | Move `cache_manager`, `data_source`, `detections_builder` to `scene_common` | ~1 hour | Phase 2 + all tests |
| 2 | Move `controller/analytics/` → `analytics/src/analytics/` | ~1 hour | Phase 3 |
| 3 | Strip inline analytics from controller (Stage F) | ~45 min | End state |

**Constraint:** Phases execute strictly in order. Each must pass all tests before the next begins.

---

## Phase 1 — Move utilities to `scene_common`

**Goal:** Break `analytics/service.py → controller` dependency chain.

### 1.1 Move three utility files

**Action:** Copy (not move) these three files from controller to scene_common:
- `controller/src/controller/data_source.py` → `scene_common/src/scene_common/data_source.py`
- `controller/src/controller/detections_builder.py` → `scene_common/src/scene_common/detections_builder.py`
- `controller/src/controller/cache_manager.py` → `scene_common/src/scene_common/cache_manager.py`

**Import fix in copied file:** In `scene_common/cache_manager.py`, update line 7:
- Old: `from controller.data_source import RestSceneDataSource, FileSceneDataSource`
- New: `from scene_common.data_source import RestSceneDataSource, FileSceneDataSource`

**Delete originals:** Once controller import locations are updated (step 1.2), delete:
- `controller/src/controller/cache_manager.py`
- `controller/src/controller/data_source.py`
- `controller/src/controller/detections_builder.py`

### 1.2 Update controller imports

**File:** `controller/src/controller/scene_controller.py`

Update line 10:
- Old: `from controller.cache_manager import CacheManager`
- New: `from scene_common.cache_manager import CacheManager`

Update lines 14–15:
- Old: `from controller.detections_builder import (buildDetectionsList,` / `                                           computeCameraBounds)`
- New: `from scene_common.detections_builder import (buildDetectionsList,` / `                                              computeCameraBounds)`

### 1.3 Update test imports + patches

**File:** `tests/sscape_tests/scenescape/test_cache_manager.py`

- Line 7: `from controller.cache_manager` → `from scene_common.cache_manager`
- Line 8: `from controller.data_source` → `from scene_common.data_source`
- Line 34 (patch): `patch('controller.data_source.RESTClient'` → `patch('scene_common.data_source.RESTClient'`
- Line 109 (patch): `patch('controller.cache_manager.log.error'` → `patch('scene_common.cache_manager.log.error'`

**File:** `tests/sscape_tests/scenescape/test_detections_builder.py`

- Line 10: `from controller.detections_builder` → `from scene_common.detections_builder`
- Line 107 (patch): `patch('controller.detections_builder.get_epoch_time'` → `patch('scene_common.detections_builder.get_epoch_time'`
- Line 241 (patch): `patch('controller.detections_builder.calculateHeading'` → `patch('scene_common.detections_builder.calculateHeading'`
- Line 242 (patch): `patch('controller.detections_builder.convertXYZToLLA'` → `patch('scene_common.detections_builder.convertXYZToLLA'`

### 1.4 Verify

```bash
pytest tests/sscape_tests/scenescape tests/sscape_tests/scene_pytest tests/sscape_tests/geometry -q --no-header -p no:django
```

Expected: 445 passed, 2 skipped ✓

---

## Phase 2 — Move analytics package to `analytics/src/analytics/`

**Goal:** `analytics/service.py` imports only from `scene_common` and `analytics.*`.

### 2.1 Create analytics package structure

**Action:** Create the following:
- `analytics/src/analytics/__init__.py` (can be empty)
- `analytics/src/analytics/adapters/__init__.py` (can be empty)
- `analytics/src/setup.py` (new; copy structure from `scene_common/src/setup.py`, change name to `analytics`)

### 2.2 Move 13 files from controller to analytics

**Files to move:** From `controller/src/controller/analytics/` → `analytics/src/analytics/`

```
engine.py
analytics_models.py
event_publisher.py
event_serializer.py
region.py
sensors.py
state.py
tripwire.py
adapters/
  ├── __init__.py
  ├── ingestion.py
  ├── publisher.py
  └── scene_model.py
service.py
```

### 2.3 Fix internal imports in moved files

**Global find-replace** across all 13 files in `analytics/src/analytics/`:
- `controller.analytics.` → `analytics.`

Examples (actual lines will vary):
- `from controller.analytics.region import ...` → `from analytics.region import ...`
- `from controller.analytics.sensors import ...` → `from analytics.sensors import ...`
- `import controller.analytics.something` → `import analytics.something`

### 2.4 Fix external imports in moved files

**File:** `analytics/src/analytics/service.py`

Update line 5 (or wherever it appears):
- Old: `from controller.cache_manager import CacheManager`
- New: `from scene_common.cache_manager import CacheManager`

Update line 6 (or wherever it appears):
- Old: `from controller.detections_builder import buildDetectionsList, computeCameraBounds`
- New: `from scene_common.detections_builder import buildDetectionsList, computeCameraBounds`

### 2.5 Update analytics entry point

**File:** `analytics/src/analytics-cmd`

Update line 11:
- Old: `from controller.analytics.service import AnalyticsService`
- New: `from analytics.service import AnalyticsService`

### 2.6 Update analytics Dockerfile

**File:** `analytics/Dockerfile`

Replace the builder stage controller package build section with analytics package build. The runtime stage should copy the `analytics` package instead of the `controller` package.

Exact changes TBD during implementation phase.

### 2.7 Delete controller analytics directory

**Action:** Delete entire `controller/src/controller/analytics/` directory.

### 2.8 Update test imports

**All 7 test files:** Replace `controller.analytics.` with `analytics.` in import statements only (no logic changes).

**Files:**
- `tests/sscape_tests/scenescape/test_event_serializer.py` (lines 6–7)
- `tests/sscape_tests/scenescape/test_analytics_models.py` (line 8)
- `tests/sscape_tests/scenescape/test_scene_controller.py` (lines 14–15)
- `tests/sscape_tests/scene_pytest/test_analytics_tripwire.py` (lines 8–10)
- `tests/sscape_tests/scene_pytest/test_analytics_sensors.py` (lines 8–9)
- `tests/sscape_tests/scene_pytest/test_scene.py` (lines 14–17, 823)
- `tests/sscape_tests/scene_pytest/test_analytics_ingestion.py` (lines 13, 127)

### 2.9 Verify

```bash
pytest tests/sscape_tests/scenescape tests/sscape_tests/scene_pytest tests/sscape_tests/geometry -q --no-header -p no:django
```

Expected: 445 passed, 2 skipped ✓

Also verify analytics image imports cleanly:
```bash
make rebuild-analytics
docker logs scenescape-analytics-1  # Should show no ImportError
```

---

## Phase 3 — Stage F: Strip inline analytics from controller

**Goal:** Controller only tracks, publishes `DATA_SCENE`. No inline event/region/tripwire processing.

### 3.1 Remove analytics imports and state from Scene

**File:** `controller/src/controller/scene.py`

Delete lines 19–27 (all `controller.analytics.*` and `controller.analytics.sensors.*` imports).

Delete line ~84: `self._ingestion = SceneDataIngestion()` and the two alias lines below it (`self._analytics_objects = ...`, `self.object_history_cache = ...`).

Delete line ~108: `self.analytics_state = AnalyticsStateStore()`.

Delete the entire `_updateEvents()` method (lines ~477–494).

**Flag:** `_isEnvironmentalSensor` uses `SceneDataIngestion._is_environmental_sensor` static method (line ~475). Extract the one-liner logic into `scene.py` directly or evaluate whether the method is still needed.

**Flag:** `_updateEnvironmentalSensorReadings` and `_updateAttributeSensorEvents` — evaluate whether these are still needed by controller's sensor pipeline or if they were purely for analytics. Check call sites.

### 3.2 Remove analytics calls from SceneController

**File:** `controller/src/controller/scene_controller.py`

Delete line 13: `from controller.analytics.event_publisher import publish_events` (now `from analytics.event_publisher...` after Phase 2, but delete entirely).

Delete lines ~478–480: The block calling `scene._updateEvents(...)`.

Delete line ~370: The call to `publish_events(scene, ...)`.

### 3.3 Verify

```bash
pytest tests/sscape_tests/scenescape tests/sscape_tests/scene_pytest tests/sscape_tests/geometry -q --no-header -p no:django
```

Expected: 445 passed, 2 skipped ✓

Also verify controller image:
```bash
make rebuild-controller
python3 -c "from controller.scene import Scene; import sys; print('analytics' in sys.modules)" 
# Expected: False or only scene_common-level analytics imports
```

---

## End-to-End Verification Checklist

After all phases:

- [ ] `make indent-check` passes
- [ ] `pytest tests/sscape_tests/scenescape tests/sscape_tests/scene_pytest tests/sscape_tests/geometry -q` — 445 passed, 2 skipped
- [ ] `make rebuild-analytics && docker logs scenescape-analytics-1` — clean, no ImportError
- [ ] `python3 -c "from analytics.service import AnalyticsService"` inside analytics container — works
- [ ] `python3 -c "from controller.scene import Scene"` inside controller container — imports cleanly, no `controller.analytics` in traceback
- [ ] `make demo --profile controller` — scenes render, objects move
- [ ] `make demo --profile tracker --profile analytics` — tracker outputs DATA_SCENE, analytics outputs DATA_REGULATED and events

---

## Architecture After Refactor

```
┌─────────────────────────────────────────────────────────┐
│ scene_common (library)                                  │
├─────────────────────────────────────────────────────────┤
│ • cache_manager                                         │
│ • data_source                                           │
│ • detections_builder                                    │
│ • chain_data, camera, transform, geometry              │
│ • mqtt, rest_client, schema, logging                   │
└─────────────────────────────────────────────────────────┘
           ↑                          ↑
           │                          │
    ┌──────┴──────┐           ┌──────┴──────┐
    │ controller  │           │  analytics  │
    │ (service)   │           │  (service)  │
    ├─────────────┤           ├─────────────┤
    │ • scene.py  │           │ • service.py│
    │ • tracker   │           │ • adapters/ │
    │ • cameras   │           │ • engine.py │
    │ • reid      │           │ • events    │
    └─────────────┘           └─────────────┘
```

Both services are independent peers. Analytics imports only from `scene_common`, never from `controller`.

---

## Decisions

1. **One copy in `scene_common`:** `cache_manager`, `data_source`, `detections_builder` — infrastructure, extractable to a future Scene Registry Service without breaking either service.
2. **Sensor utilities stay in analytics:** `update_attribute_sensor_events`, `update_environmental_sensor_readings` — controller sensor pipeline ownership TBD in Phase 3 implementation.
3. **Backward-compat note:** Existing `ANALYTICS_ONLY` environment variables and `ControllerMode.isAnalyticsOnly()` branches remain active; dead code cleanup deferred to follow-on pass.
4. **Order matters:** Phases must execute in sequence. Do not mix changes across phases.

---

## Timeline Estimate

- Phase 1: ~1 hour (file copies, import renames, test updates)
- Phase 2: ~1 hour (directory move, find-replace, Dockerfile update, test renames)
- Phase 3: ~45 minutes (remove 20 lines, verify semantics)
- **Total:** ~2.75 hours

---

## Next Step

Proceed with Phase 1 implementation.
