<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Camera Visibility Pass-Through and Tracker FOV Parity

## Canonical baseline

**Controller-proper** (Scene Controller with a local tracker, default mode) is the
source of truth for how analytics should behave: reliability gating, visibility
before events, regulated/event field content, etc.

**Controller analytics-only mode** was a transitional compromise so Tracker could
run while analytics still lived in the Controller. It is **not** the product
contract. Do not treat analytics-only bypasses (e.g. skipping the `frameCount`
reliability gate) as regressions to restore.

Standalone Analytics should match **Controller-proper** semantics, with MQTT
track input replacing the in-process tracker.

ADRs ([ADR 7](../../docs/adr/0007-tracker-service.md),
[ADR 13](../../docs/adr/0013-controller-breakdown-microservices.md)) call for
analytics/events **parity** with that Controller-proper behavior as
responsibilities move out of the monolith — not parity with analytics-only
quirks.

---

## Goal

Ensure every track and every analytics event can answer:

1. **Per track** — which cameras’ FOVs contain this object (`visibility`).
2. **Per incident / event** — which camera views are available for the objects in
   the event (union of per-object `visibility`).
3. **Future shape reconstruction** — per-camera pixel boxes (`camera_bounds`) on
   regulated / event snapshots when configured.

Ownership model (agreed):

| Concern | Owner |
| ------- | ----- |
| Compute track-time FOV `visibility` | Track producer (Controller today; Tracker when at parity) |
| Prefer pass-through; fill only when missing | Analytics |
| Assemble events / regulated; must not drop `visibility` | Analytics |
| `camera_bounds` on regulated (and events when needed) | Analytics when `visibility_topic=regulated`; Controller when `unregulated` on its own topics |

ADRs list camera visibility under Analytics capabilities. They do **not**
redefine publish order or drop `visibility` from events.

---

## Reliability gate (related review item)

Controller-proper gates region/tripwire analytics on track maturity
(`frameCount > MIN_FRAMES_FOR_RELIABLE_TRACK`). Commit `8d927d12` moved that
policy into the analytics engine for **all** paths, using
`len(publishedLocations) > 3` as a tracker-independent proxy so MQTT analytics
and the old in-process path share one filter.

| Baseline | Verdict |
| -------- | ------- |
| vs analytics-only (skipped the gate) | **Not a bug** — analytics-only was transitional |
| vs Controller-proper (`frameCount > 3`) | **Policy aligned**; proxy may differ from producer `frame_count` |

**Optional polish (not a P0 fix):** when MQTT supplies `frame_count`, prefer it
for the reliability gate and fall back to `publishedLocations` length only when
absent — closer to Controller-proper’s signal without restoring the
analytics-only bypass.

---

## Incident camera semantics (product)

Two meanings of “cameras for this incident” — do not conflate them:

### A. Object / track FOV visibility (v1 — this plan)

For each object in the event (`objects` / `entered` / `exited`), use that
track’s `visibility` list (FOV contains `sceneLoc`).

**Incident camera set** = union of those lists.

- Answers: “Which live views can show this person/vehicle?”
- Matches Controller-proper `_updateVisible` semantics.
- Pairs with `camera_bounds` for future shape reconstruction.

### B. Region / tripwire coverage (later, optional)

Cameras whose FOV intersects the ROI / tripwire geometry even if no object is
present.

- Answers: “Which cameras cover this zone?”
- Analytics geometry join; optional event field (e.g.
  `metadata.covering_cameras`).
- **Out of scope for this plan.**

---

## Part 1 — Analytics FOV pass-through

### Status

| Item | Status |
| ---- | ------ |
| `AnalyticsObject.visibility` + adapter copy | Done |
| `_updateVisible` only when `visibility is None` (preserve `[]`) | Done |
| Order: `_updateVisible` → `_updateEvents` → regulated publish | Done |
| `scene-data.schema.json` allows `visibility` / Controller extras | Done |
| Scene-data schema validation restored on Analytics ingest | Done |
| Event payloads include `visibility` via serializer `hasattr` | Done (depends on model + order) |
| `camera_bounds` on event payloads | Not done (regulated path only today) |
| Docs: analytics data formats note pass-through / fallback | Not done |
| Functional test: event MQTT contains `visibility` | Not done |

### Remaining Analytics work

1. **Optional: event `camera_bounds`**
   - When `visibility_topic=regulated`, ensure event object snapshots can carry
     `camera_bounds` (pass-through from ingest if present, else
     `computeCameraBounds` for cameras in `visibility`).
   - Needed for incident self-contained shape reconstruction without replaying
     regulated stream.

2. **Docs**
   - Update
     `docs/user-guide/microservices/analytics/data_formats.md` (and Controller
     note if needed): producer owns FOV; Analytics pass-through + fallback;
     incident camera set = union of object `visibility`.
   - State clearly that behavior targets **Controller-proper** parity, not
     legacy analytics-only mode.

3. **Tests**
   - Unit: already cover pass-through / empty preserve / call order.
   - Add functional or integration coverage that a region/tripwire event object
     includes `visibility` when Controller (or Analytics fallback) supplied it.

4. **`visibility_topic` contract (confirm in docs)**
   - Default `regulated` on both services.
   - Controller: emits `visibility` IDs on `data/scene` / `external`; does **not**
     attach `camera_bounds` when topic is `regulated`.
   - Analytics: pass-through `visibility`; attach `camera_bounds` on regulated
     (and optionally events) when topic is `regulated`.
   - Avoid both services projecting bounds for the same hop.

### Estimate (remaining Analytics)

~0.5–1 day (docs + event bounds if in scope + one functional assertion).

---

## Part 2 — Tracker FOV parity (Controller-proper equivalent)

### Problem

Standalone Tracker does **not** emit `visibility`. Analytics falls back to local
FOV recompute. That works but:

- Duplicates geometry work.
- Risks drift vs Controller-proper FOV (horizon, resolution, edge cases).
- Breaks the preferred “producer computes, Analytics pass-through” model for
  `demo-tracker`.

Tracker today has intrinsics/extrinsics and pose matrices, but:

- Does not parse/store camera **resolution** (Manager API already returns it).
- Has no ground FOV polygon (`regionOfView`) or point-in-FOV helper.
- Publish path has no `visibility` field on `Track` / serialize.

### Approach: Controller-proper FOV (recommended)

Do **not** use detection-association (“cameras that saw this detection this
chunk”) — wrong for incident views.

Do **not** use a cheap world→pixel / in-frame approximation as the long-term
contract — semantic drift vs Controller-proper.

**Port Controller FOV:**

1. Parse `resolution` (`width`/`height`) into `tracker::Camera` from API/file
   scene load.
2. At worker (or transformer) init, build a ground FOV quad per camera
   (mirror `CameraPose._calculateRegionOfView`: frame corners → normalized →
   world / horizon cull → polygon).
3. For each reliable track, test `sceneLoc` against each camera FOV
   (point-in-polygon); fill `Track::visibility`.
4. Emit `visibility` in `TrackPublisher::serialize` (schema already allows it).
5. Unit tests with fixed extrinsics/resolution (in/out points, multi-camera);
   maintain Tracker coverage gates (≥90% line, ≥50% branch).
6. Design/docs: tracker implementation note + scene-data field description.

### Key files (expected)

- `tracker/inc/scene_loader.hpp` / `scene_parser` — store resolution
- `tracker/src/api_scene_loader.cpp` — pass through API `resolution`
- New helper (e.g. `camera_fov.hpp` / beside `coordinate_transformer`)
- `tracker/inc/tracking_types.hpp` — `std::vector<std::string> visibility`
- `tracker/src/tracking_worker.cpp` — fill after `convert_tracks`
- `tracker/src/track_publisher.cpp` — serialize array
- `tracker/test/unit/*` — FOV + publisher tests
- `tracker/docs/implementation.md` (or How-to) — brief behavior note

### Estimate

| Scope | Effort |
| ----- | ------ |
| Resolution parse + FOV helper + emit + unit tests | **~2–4 engineer-days** |
| Plus `camera_bounds` on Tracker output (optional, not required for pass-through of IDs) | **+1–2 days** |

Risk: matching Python horizon / missing-resolution edge cases. Mitigate with
shared golden fixtures (same camera pose → same visibility IDs as Controller
`_updateVisible`).

### Acceptance criteria (Tracker)

- [ ] Tracker `data/scene` objects include `visibility: string[]` when cameras
      have pose + resolution.
- [ ] Analytics receives Tracker messages and **does not** overwrite non-null
      producer `visibility` (pass-through path exercised).
- [ ] For a shared test pose, Tracker visibility IDs match Controller-proper FOV
      for the same world point (documented fixture).
- [ ] Unit coverage thresholds still pass.
- [ ] Schema/examples/docs updated.

---

## Phasing

| Phase | Work | Depends on |
| ----- | ---- | ---------- |
| **P0 (done on branch)** | Analytics pass-through, order fix, schema ingest looseness, schema validation | — |
| **P1** | Analytics docs + functional event `visibility` check; optional event `camera_bounds` | P0 |
| **P2** | Tracker Controller-proper FOV emit | P0 (schema ready) |
| **P3 (optional)** | Incident field for region covering cameras (semantics B) | P1/P2 |
| **P4 (optional)** | Tracker or Analytics `camera_bounds` enrichment for shape reconstruction | Product need |
| **P5 (optional)** | Reliability gate prefers MQTT `frame_count` when present | Product / polish |

Suggested merge strategy: land P0/P1 with Analytics branch; Tracker P2 as a
follow-up PR against Tracker + schema/docs.

---

## Out of scope

- Region/tripwire “covering cameras” event metadata (semantics B).
- Restoring analytics-only reliability-gate bypass.
- Moving the FOV owner to a future Spatial Transform service (ADR 13) — revisit
  when that service exists; until then producer + Analytics fallback.
- Changing default `visibility_topic` away from `regulated`.
- Unbounded `publishedLocations` growth (separate hygiene item).

---

## References

- Controller FOV: `controller/src/controller/scene.py` (`_updateVisible`)
- Controller FOV geometry: `scene_common/.../transform.py` (`_calculateRegionOfView`)
- Analytics pass-through: `analytics/.../adapters/scene_model.py` (`_updateVisible`)
- Analytics handler order: `analytics/.../service.py` (`handleSceneDataMessage`)
- Reliability unify: commit `8d927d12` (`bugfix: reliable tracks moved to engine`)
- Ingest schema: `tracker/schema/scene-data.schema.json`
- ADR 13 Analytics role: camera visibility + events parity with Controller-proper
