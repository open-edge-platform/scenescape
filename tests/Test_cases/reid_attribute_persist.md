<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ReID Gender Persist — Test Cases

Test cases for the persistent-attribute (gender) storage-to-VDMS scenario.

**Relevant configuration:**

- `persist_attributes: {"person": ["gender"]}`
- `feature_accumulation_threshold: 12`, `minimum_bbox_area: 5000`,
  `similarity_metric: L2`, `similarity_threshold: 30.0`,
  `stale_feature_timeout_secs: 5.0`
- VDMS confidence threshold for TIER-1 constraints: `0.8`

---

## Test Cases

### TC-01

**Title:** Persisted attribute stored to VDMS on track end

**Summary:** When `persist_attributes: {person: [gender]}` is configured, a
person's gender is written to the VDMS `reid_vector` descriptor when the track
ends.

**Steps:**

1. Configure `persist_attributes: {"person": ["gender"]}` in
   `controller/config/tracker-config.json`, restart the `scene` service.
2. Feed a person video where the detector emits `gender=Male` (conf >= 0.8).
3. Let the track accumulate >= 12 embeddings (`reid_state` reaches
   `query_no_match`).
4. Let the person leave the scene, wait ~6 s (`stale_feature_timeout_secs`).
5. Query VDMS: `FindDescriptor` on set `reid_vector`, results list `["uuid", "persist", "persist_timestamp"]`; decode `persist` JSON and verify it contains `gender`.

**Expected results:**

- A descriptor exists with the track's `uuid` and a non-empty `persist` field whose JSON contains `gender` (e.g., `{"label": "Male"}`).
- Controller log shows `_addNewFeaturesToDatabase: Adding N features ... gid=<uuid>`.

---

### TC-02

**Title:** Persisted attribute appears in scene output during a continuous track

**Summary:** `persistent_data.gender` is published while the person is tracked.

**Steps:**

1. With `persist_attributes` configured, feed a person with `gender=Male`.
2. Subscribe to `scenescape/regulated/scene/<scene_id>`.

**Expected results:**

- The tracked object includes `persistent_data.gender` with `label=Male`.

---

### TC-03

**Title:** Gender survives intermittent detector dropouts within one track

**Summary:** `setPrevious()` fill-if-None keeps gender alive when some frames
omit it.

**Steps:**

1. Feed a continuous track where gender is present in frame 1, absent in
   frames 2-5, present again later.

**Expected results:**

- Every published frame retains `persistent_data.gender.label == "Male"`
  (value never drops to null mid-track).

---

### TC-04

**Title:** High-confidence gender used as TIER-1 VDMS constraint

**Summary:** Gender with confidence >= 0.8 is applied as an AND constraint in
the similarity query.

**Steps:**

1. Store a Male person to VDMS.
2. Re-enter with `gender=Male` conf >= 0.8, observe controller debug log for
   query constraints.

**Expected results:**

- Log shows `ADDED: gender=Male` in TIER-1 constraints, match returns the
  same UUID.

---

### TC-05

**Title:** No `persist_attributes` configured -> no `persistent_data` in output

**Summary:** Without config, gender is not surfaced as persistent data (though
still stored to VDMS via the metadata path).

**Steps:**

1. Remove/omit `persist_attributes` from tracker-config, restart the `scene`
   service.
2. Feed a person with `gender=Male`, inspect scene output.

**Expected results:**

- Objects have `metadata.gender` but **no** `persistent_data` field.

---

### TC-06

**Title:** Low-confidence gender is NOT used as a hard match constraint

**Summary:** Gender with confidence < 0.8 must not filter candidates in TIER 1
(falls back to vector similarity).

**Steps:**

1. Store a person to VDMS with gender.
2. Re-enter with `gender` conf = 0.63, observe query constraints and match
   outcome.

**Expected results:**

- Log shows `IGNORED: gender (confidence ... < 0.8 ...)`.
- Match still succeeds via vector similarity (not blocked by gender mismatch).

---

### TC-07

**Title:** VDMS descriptor set missing dimension metadata, resulting in discarded embeddings

**Summary:** Regression guard for the "stuck in `pending_collection`" failure.

**Steps:**

1. Put VDMS in a state where `reid_vector` exists but returns no dimensions
   (or start the controller against such a set).
2. Feed a person and observe state + logs.

**Expected results:**

- Controller logs `ReID schema initialization failed: ensureSchema:
  'reid_vector' exists but returned no dimensions`.
- Track stays `reid_state == "pending_collection"`, `similarity == null`
  indefinitely.
- After recreating the descriptor set + restart, log shows `Inferred ReID
  embedding dimensions from first observed vector: 256` and state advances.

---

### TC-08

**Title:** Bounding box below minimum area, so no features were gathered

**Summary:** Frames with bbox area <= `minimum_bbox_area` (5000) do not
contribute embeddings.

**Steps:**

1. Feed a person whose bbox is consistently < 5000 px area.

**Expected results:**

- `reid_state` never leaves `pending_collection`, log shows `Bbox too small for
  rv_id=...`.

---

### TC-09

**Title:** ReID disabled -> immediate `reid_disabled` state, no query

**Summary:** When ReID is disabled (e.g., query-time threshold exceeded or
disabled config), no matching occurs.

**Steps:**

1. Force `reid_enabled = False` (or exceed max query time).
2. Feed a person.

**Expected results:**

- `reid_state == "reid_disabled"`, `similarity == null`, no VDMS query issued.
