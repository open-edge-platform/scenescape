<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# External Platform Citizenship: Objects + Cams (No `data/source`)

## Status

Planned. Coordinates two in-flight branches before merge:

- `ITEP-97980_handling_moving_external_objects` — ADR 16 moving agents /
  nested cameras (currently also introduces `scenescape/data/source`)
- `handheld-app-support-features` — unlocked Cams, ephemeral pose/optics,
  `pose_provenance` (ADR 18)

North star: **everything as an object** in one scene graph (static + dynamic),
with a loggable materialized state. That graph store and unified output model
do **not** exist yet; this plan does not build them. It stops a third
citizenship plane (`data/source`) and splits near-term work so both PRs align
with the endgame.

## Problem

Two valid “moving sensor” stories landed on diverging representations:

| Concern | Handheld branch | 97980 branch today |
| ------- | --------------- | ------------------ |
| Mover identity | Registered `Cam` | `source_id` + optional object |
| Ingest | `scenescape/data/camera/{id}` | `scenescape/external/{publisher}/{type}` |
| How pose reaches UI | Regulated cameras + provenance | Retained `scenescape/data/source/...` |
| Authority | `pose_locked` | Trust list + TTL pose cache |

`data/source` special-cases platforms outside the object and Cam models. That
breaks the ethos that a scene is a composite of objects, and that a camera is
a sub-scene (extra transform + optics)—not a parallel MQTT product surface.

Ultimate option 1 (full object/sub-scene graph on output + datastore) needs
architecture that Scenescape does not have yet. Pure option 2 (everything is a
Cam) fights ADR 16’s unregistered-agent model. Least resistance that still
points at the endgame:

- Camera-like devices → Cam path (handheld)
- Dynamic agents → ADR 16; **platform P is a scene object**
- Nested `cameras[]` → wire encoding of child sub-scenes for ingest only
- **`data/source` is not a product surface**
- Agent frustums → **Bar A** (object/regulated metadata), not Cams and not
  `data/source`

## Goals

- Merge both branches without leaving `data/source` as a supported API on
  `main`.
- Clear citizenship split documented on both PRs and in ADR 16.
- 97980: platform presence via **scene object output**, not retained source
  snapshots.
- Handheld: Cam live pose / provenance only; no agent viz via `data/source`.
- Restore DynamicSources-level multi-cam frustums via Bar A **after** P is on
  the object path (separate PR).

## Non-goals (this plan’s near-term PRs)

- Building the scene-graph datastore or unified static+dynamic output feed
  (Phase 4 epic).
- Deleting ADR 16 or forcing all agents to pre-register as Cams.
- Frustums in the first 97980 reshape merge (body object/asset is enough;
  Bar A is the next PR).
- Full SceneCamera parity (calibration UI, video, distortion, footprints).
- Camera↔external path fusion / co-observation (ADR 16 Future Work).
  Same-platform multi-cam batching into one tracker tick is in scope for
  97980 ingest; cross-path fusion is not.

## Design summary

### Scene graph intuition (target)

```text
Scene S
└── Platform P          # object: pose T_S←P
    ├── Camera C1       # sub-scene: mount T_P←C1 + intrinsics
    └── Camera C2
```

`T_S←Ci = T_S←P ∘ T_P←Ci`. Nested `cameras[]` on the wire already encodes this;
after ingest, citizenship must be objects (and Cams where appropriate)—not a
retained source topic.

### Near-term citizenship

1. **Handheld / unlocked Cams** — first-class Cams; live extrinsics on
   `data/camera/{id}`; UI follows regulated `pose_provenance.class === "live"`.
2. **ADR 16 agents** — publish `external/{P}/{thing_type}`; controller upserts
   scene object **P** (`id == source_id`, typically `track=false`) including on
   pose-only / empty observation ticks; detections attributed to `P` or
   `P:Ci`.
3. **Internal only** — `ExternalSourcePoseCache` TTL may remain for pose reuse;
   it must not publish `DATA_SOURCE`.
4. **Frustums (Bar A)** — UI reads P pose + Ci mount/intrinsics from
   scene/regulated object (or companion object metadata), reusing today’s
   pinhole frustum math—not a new MQTT family.

---

## PR layering and count

### Near-term merge train: **4 PRs**

| # | PR | Branch / base | Depends on | Purpose |
| - | -- | ------------- | ---------- | ------- |
| **1** | Handheld Cam live pose | `handheld-app-support-features` → `main` | — | Unlock, ephemeral pose/optics, ADR 18 provenance, Cam UI follow |
| **2** | Remove `data/source` | stacked on reshaped 97980 (or 97980 after rebase on post-1 `main`) | Prefer after **1** (required before 97980 lands on `main`) | Delete product DATA_SOURCE path; keep ADR 16 ingest + internal pose cache |
| **3** | Platform as scene object | stacked on **2** | **2** | Emit/update P on object output (incl. pose-only); docs/tests; no frustums yet |
| **4** | Frustum parity (Bar A) | new branch from `main` after **3** | **3** | Carry Ci mount/intrinsics on object path; retarget UI frustum renderer |

Phase 0 (contract bullets) is **not** a separate PR—fold into PR **1** and
PR **2**/**3** descriptions (and a small ADR 16 note in **2** or **3**).

### Why this granularity

- **1 alone:** Cam story reviewable without agent/MQTT churn.
- **2 alone:** Pure deletion / API removal—easy to review and revert; proves
  nothing on `main` still needs `DATA_SOURCE`.
- **3 alone:** Behavior add (P citizenship) without mixing delete diffs.
- **4 alone:** UI + output schema for frustums; does not block agent object
  merge; avoids holding 97980 for viz polish.

Stack **2** then **3** on the same 97980 line of work (two PRs or two clear
commits opened as stacked PRs). Do **not** merge current 97980 with
`data/source` still present.

### Later epic (not in the 4): **~3–5 more PRs** (indicative)

Phase 4 backlog when the datastore/output work starts—for example:

1. Scene-graph output schema (nodes/edges on one feed)
2. Append-only log + materialized snapshot query
3. Promote nested Ci to first-class graph children in that feed
4. Calibration-resolution unification (ADR 16 Future Work)
5. Optional: richer frustum (resolution-true FOV, footprints)—still not
   SceneCamera/video unless product asks

**Total discussed for the dual-branch alignment: 4 PRs.**  
**Total if Phase 4 is counted vaguely: ~7–9 PRs** over a longer horizon.

---

## Merge order

```text
PR1  Merge handheld → main
     (Phase 0 text on PR body)

PR2  Rebase 97980 on main → strip data/source → merge
PR3  Platform as object (on top of PR2) → merge
     Smoke: body visible as object/asset

PR4  Bar A frustum parity → merge

Epic Phase 4 scene-graph store / unified output (separate)
```

**Why handheld first:** Avoids baking `data/source` into `main` for Cam
reviewers. If handheld slips, still land **PR2** before any 97980 merge—never
ship `data/source` as supported API.

### Overlap files (expect rebase conflict after PR1)

- `controller/src/controller/scene_controller.py`
- `controller/src/controller/scene.py`
- `controller/src/schema/metadata.schema.json`
- `docs/user-guide/microservices/controller/data_formats.md`
- `docs/user-guide/microservices/analytics/data_formats.md`
- `docs/user-guide/how-to-guides/publish-external-source-adapter.md`
- `manager/src/manager/static/js/scenescape3d.js`
- `scene_common/src/scene_common/ingestion.py`
- `tests/sscape_tests/scenescape/test_scene_controller.py`
- `.github/resources/cognitive-complexity-baseline.txt`

Resolution rule: **handheld wins Cam/runtime pose; 97980 wins external ingest
and object emission; neither keeps product `DATA_SOURCE`.**

---

## Phase 0 — Shared contract (on PR bodies, not a fifth PR)

Same three bullets on PR **1** and PR **2**/**3**:

1. Camera-like devices → `data/camera/{id}` + regulated cameras +
   `pose_provenance` (handheld / ADR 18).
2. Dynamic agents → `external/{publisher}/{type}`; platform **P** is a **scene
   object**; nested `cameras[]` are wire children for transform/ingest only.
3. `scenescape/data/source` is **not** a product surface—remove or never merge;
   internal pose cache only.

Suggested one-liners:

- PR1: “Live Cam pose via unlock + provenance; agents remain ADR 16 / out of
  scope.”
- PR2: “Remove `data/source`; keep ADR 16 ingest and internal pose cache.”
- PR3: “External platforms as scene objects; nested cameras for ingest only.”
- PR4: “Agent camera frustums from object metadata (Bar A); no `data/source`.”

---

## PR1 — Handheld (`handheld-app-support-features`)

### Keep / finish

- Cam `pose_locked`, ephemeral extrinsics/optics, retention across config
  refresh.
- ADR 18: `pose_provenance` on pose writes; regulated `cameras[]`; UI follow
  on `class === "live"`.
- Docs: handheld guide, pose lock API, analytics formats.
- Phase 0 bullets on PR description.

### Must not own

- `DATA_SOURCE`, `dynamicsources.js`, ADR 16 nested-camera viz.
- Platform-as-object for agents.
- Scene-graph datastore.

### Exit criteria

- Merged to `main`.
- Unlocked handheld Cam follows regulated provenance.
- ADR 18 language on `main`.

---

## PR2 — Remove `data/source` (97980 reshape A)

Rebase 97980 onto post-PR1 `main` first when possible.

| Remove / stop shipping | Notes |
| ---------------------- | ----- |
| `controller/src/controller/source_state.py` | Prefer delete |
| `SourceStatePublisher` wiring / `on_remove` MQTT | In `scene_controller` |
| `PubSub.DATA_SOURCE` topic (if unused elsewhere) | Confirm no other consumers |
| `manager/.../dynamicsources.js` + `scenescape3d.js` hook | |
| `constants.js` `DATA_SOURCE` | |
| `user_access_config.json` DATA_SOURCE ACLs | |
| Schema / docs `source_state` as consumer contract | |
| `tests/.../test_source_state.py`, DATA_SOURCE renderer tests | Drop or gate until PR4 |
| Docs “Resolved External Source State Output” | Point at upcoming object citizenship (PR3) |

**Keep:** ADR 16 ingest, nested `cameras[]` for localization, internal
`ExternalSourcePoseCache`.

### Exit criteria

- Grep-clean of product `DATA_SOURCE` / `dynamicsources`.
- Existing external ingest unit tests still green (no reliance on source-state
  publish).

---

## PR3 — Platform as scene object (97980 reshape B)

Depends on PR2.

- On accepted external pose (including empty objects / pose-only): ensure
  object **P** with stable `id == source_id`, typically `track=false`, category
  / asset for the body, pose in scene frame.
- Empty measurement / pose-only still advances publish path so P updates and
  ages without retained source snapshots.
- Nested `cameras[]`: keep compose + detection attribution (`P:Ci`); **do not**
  yet require mount/intrinsics on object output (that is PR4).
- Docs: platform-as-object guidance; ADR 16 roadmap note (Phase 0).
- Tests: pose → P on object path; pose-only → P; no DATA_SOURCE.

### Conflict resolution vs handheld (during rebase)

| File | Rule |
| ---- | ---- |
| `scene_controller.py` | Keep handheld Cam path; keep 97980 external ingest; **no** source-state publish |
| `scene.py` | Keep observation→world / rotation **and** handheld pose-retain helpers |
| `metadata.schema.json` | Union external `cameras[]` + handheld pose fields; no `source_state` output |
| `data_formats.md` | Separate Cam-live vs external-agent-object sections |
| `scenescape3d.js` | Handheld Cam follow only |
| `test_scene_controller.py` | Merge both suites; no source-state expectations |

### Exit criteria

- Smoke: adapter / `drone_sim` → platform visible as **object/asset**.
- Handheld Cam follow still works on `main`.

---

## PR4 — Frustum parity (Bar A)

Depends on PR3. Aligns with north star: frustums are rendering of object-graph
state, not Cam registration and not `data/source`.

### Scope = DynamicSources-level parity (not SceneCamera)

Restore:

- Body at `T_S←P`
- N child frustums: mount `T_P←Ci` + ideal pinhole from `fx/fy/cx/cy`
  (same centered-principal-point approximation as today unless cheap to fix)
- Lifetime / removal when P (or camera list) goes stale
- Select / frustum visibility toggle as before

Explicitly **out of** PR4: distortion-aware boundaries, ground footprints,
video projection, calibration gizmos, `pose_locked` (those stay Cam/handheld).

### Work items

1. **Output contract** — On P’s scene/regulated object (or agreed metadata
   envelope), publish stable camera list:
   `{ id, mount: { translation, rotation }, intrinsics, optional distortion }`
   whenever pose is accepted and cameras are known (including pose-only ticks
   that refresh body pose but keep last camera config if policy allows).
2. **Controller** — Project cached `cameras[]` (sans observations) onto that
   object output; composed scene pose already on P.
3. **UI** — Retarget frustum builder (logic from `dynamicsources.js`) to
   consume scene/regulated object updates for platform category / flagged
   objects; parent frustums under body mesh; drop any residual DATA_SOURCE
   subscription.
4. **Expiry** — Drive removal from object age-out / absence, not MQTT retain
   tombstones.
5. **Tests** — Schema/unit for camera list on P; renderer or JS unit for
   frustum from fixture object payload; no `data/source` in fixtures.

### Exit criteria

- Multi-cam drone shows body + frustums without `DATA_SOURCE`.
- Docs describe frustums as derived from object state (Bar A).

---

## Phase 4 — Follow-on epic (after the 4 PRs)

Track separately; indicative further PRs (~3–5), not blocking PR1–4:

1. Scene-graph **output** model (static + dynamic nodes on one feed).
2. Append-only log + **materialized state** store / query.
3. First-class graph children for Ci in that feed.
4. Unify camera vs external calibration resolution (ADR 16 Future Work).
5. Optional richer viz (resolution-true FOV, footprints)—still object-fed.

## Parallelism while waiting

| Owner | Now |
| ----- | --- |
| Handheld | Finish PR1; Phase 0 text; avoid DATA_SOURCE |
| 97980 | Draft PR2 deletion on current branch; draft PR3 P-as-object; rebase when PR1 lands |
| Both | Agree platform object category/asset; `id == source_id` rule |
| After PR3 | Open PR4 Bar A |

## Risks

| Risk | Mitigation |
| ---- | ---------- |
| UI loses drone frustum between PR2 and PR4 | Accept body-only gap; do not resurrect DATA_SOURCE; prioritize PR4 |
| Large `scene_controller.py` rebase | PR1 first; citizenship resolution rule |
| `source_state` left in schema | Remove in PR2 |
| Empty external ticks skip P | PR3 pose-only → object upsert test |
| PR2+PR3 stacked review fatigue | Keep PR2 delete-only; PR3 behavior-only |

## References

- `docs/adr/0016-unified-external-source-ingestion.md`
- `docs/adr/0018-camera-pose-provenance.md` (handheld branch)
- ADR 13 scene-graph direction (pose + observations per sub-scene)
- Branches: `ITEP-97980_handling_moving_external_objects`,
  `handheld-app-support-features`
- Former frustum implementation (deleted with PR2; restore math from git for PR4):
  `manager/src/manager/static/js/dynamicsources.js`
