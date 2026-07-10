# Plan: Phase 5 — Shadow Mode Parity Validation

## TL;DR
Run the analytics-adapter path (MQTT-ingestion) in parallel with the tracker path on every frame.
Compare their event outputs before publishing clears state, and log divergences.
No published output is changed; shadow runs are observability-only.

## Key architectural insight
`handleMovingObjectMessage` (tracker path) calls `publishDetections` before `publishEvents`.
`publishSceneDetections` (called inside `publishDetections`) writes the MQTT-serialized objects
into `jdata['objects']`. At that moment:
- Primary `analytics_state` is populated but NOT yet cleared
- The serialized object list is already in MQTT dict form — exactly what the analytics adapter ingests

This window is the shadow comparison point: run shadow analytics on `jdata['objects']`, compare
to primary `analytics_state`, THEN let `publishEvents` run and clear state as normal.

## Steps

### Phase A — Add shadow mode flag
1. Extend `ControllerMode.initialize(shadow_mode=False)` with a `_shadow_mode` class variable
   and `isShadowMode()` classmethod. Activated by `ANALYTICS_SHADOW_MODE=1` env var.
   *File*: `controller/src/controller/controller_mode.py`

### Phase B — Per-scene shadow state
2. In `Scene.__init__`, when `isShadowMode()`, initialise:
   - `self.shadow_ingestion = SceneDataIngestion()`
   - `self.shadow_state = AnalyticsStateStore()`
   Otherwise set both to `None`.
   *File*: `controller/src/controller/scene.py`

### Phase C — Shadow comparison helpers
3. Create `controller/src/controller/analytics/shadow.py` with four functions:

   **`run_shadow(detection_type, raw_objects, scene, now, now_str)`**
   Ingests via `scene.shadow_ingestion`, wraps via `moving_object_to_analytics_object`,
   calls `process_frame(..., scene.shadow_state)`.

   **`compare_states(primary_state, shadow_state, scene_id, detection_type)`**
   Compares per-region object counts, entered gids, exited gids, and tripwire objects.
   Logs WARN per divergence; returns divergence count (int).
   Comparison keys: `{region_key: {objects: set[gid], entered: set[gid], exited: set[gid]}}`,
   `{tripwire_key: {objects: list[(gid, direction)]}}`.

   **`build_event_dicts(scene, state, ts_str, scene_controller)`**
   Mirrors the per-event loop inside `publishEvents`, calling the existing
   `_buildAllRegionObjsList` / `_buildEnteredObjsList` / `_buildExitedObjsList` on the given
   `state`. Returns `{event_topic: event_dict}`. Reuses existing serialization — no duplication.

   **`compare_events(primary_events, shadow_events, scene_id)`**
   For each topic: compares `counts` (exact), entered id-sets (exact), exited id-sets (exact),
   and per-object dwell within ±1 s tolerance. Ignores float fields (position, velocity) to
   avoid tracker-vs-MQTT-deserialised noise. Logs WARN per structural divergence; returns
   divergence count (int).

### Phase D — Wire shadow into handleMovingObjectMessage
4. In `scene_controller.py`, in the `for detection_type in detection_types:` loop,
   after `self.publishDetections(...)` (when `jdata['objects']` is now the serialized list)
   and before `self.publishEvents(...)` (primary state still populated, not yet cleared):
   ```python
   if ControllerMode.isShadowMode() and scene.shadow_ingestion is not None:
       ts_str = jdata['timestamp']
       run_shadow(detection_type, jdata['objects'], scene, msg_when, ts_str)

       # State-level: which objects entered/exited/in-region
       divergences = compare_states(scene.analytics_state, scene.shadow_state,
                                    scene.uid, detection_type)

       # Event-level: structural payload comparison (no float positions)
       primary_evts = build_event_dicts(scene, scene.analytics_state, ts_str, self)
       shadow_evts  = build_event_dicts(scene, scene.shadow_state,    ts_str, self)
       divergences += compare_events(primary_evts, shadow_evts, scene.uid)

       if divergences:
           metrics.inc_shadow_divergence(detection_type, divergences)
   ```
   *File*: `controller/src/controller/scene_controller.py`

### Phase E — Tests
5. Unit tests for `compare_states`:
   - exact match → 0 divergences
   - shadow has extra entered object → 1 divergence
   - shadow missing an exited object → 1 divergence
   - count mismatch → 1 divergence
   - tripwire direction mismatch → 1 divergence

   Unit tests for `compare_events`:
   - identical event dicts → 0 divergences
   - entered id-sets differ → 1 divergence
   - counts differ → 1 divergence
   - dwell within ±1 s → 0 divergences
   - dwell outside ±1 s → 1 divergence
   - extra event topic in shadow only → 1 divergence

   *File*: `tests/sscape_tests/scenescape/test_analytics_shadow.py`

6. Integration smoke test: single-frame scenario where a person enters a region
   — verify both `compare_states` and `compare_events` report 0 divergences after warmup.

## Relevant files
- `controller/src/controller/controller_mode.py` — add `_shadow_mode`, `isShadowMode()`
- `controller/src/controller/scene.py` — add `shadow_ingestion`, `shadow_state`
- `controller/src/controller/analytics/shadow.py` — NEW: `run_shadow`, `compare_states`, `build_event_dicts`, `compare_events`
- `controller/src/controller/scene_controller.py` — wire shadow in `handleMovingObjectMessage`
- `tests/sscape_tests/scenescape/test_analytics_shadow.py` — NEW: unit tests for both compare functions

## Verification
1. Run `make indent-check` — passes
2. `pytest tests/sscape_tests/ -p no:django` — 440+ pass, 0 regressions
3. Enable `ANALYTICS_SHADOW_MODE=1`, replay a scene with region enter/exit — no divergences logged after warmup frame
4. Intentionally break `process_frame` → verify divergence is logged at WARN

## Decisions
- Shadow is **observability-only**: no published output changes, no shadow MQTT messages
- Shadow warmup divergences (first frame, objects already in region) are expected and logged at DEBUG, not WARN
- `jdata['objects']` is available after `publishDetections` in tracker mode only; shadow is skipped in analytics-only mode
- `SceneDataIngestion` + `AnalyticsStateStore` per scene (on Scene instance), not a global manager
- `build_event_dicts` reuses `_buildAllRegionObjsList` etc. — no duplication of serialization logic
- Float fields (position, velocity) excluded from `compare_events`; structural fields only (counts, id-sets, dwell ±1 s)
- Both `compare_states` and `compare_events` must report 0 divergences after warmup before Phase 6 cutover

## Open questions
- Should `ANALYTICS_SHADOW_MODE` also be wired into the Makefile `.env` target (alongside `CONTROLLER_ENABLE_ANALYTICS_ONLY`)?
- Should `metrics.inc_shadow_divergence` be a new counter or reuse an existing label on an existing counter?
- Warmup suppression: suppress WARN for the first N frames per scene, or accept first-frame noise?
- Should `compare_states` emit a structured log entry (JSON) to make divergences grep-able in CI?
