<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Tracker Metrics Evaluation — Phase 2 Plan (ITEP-92875)

**Release:** Scenescape 2026.3
**Basis:** [ADR 9 — Tracking Evaluation Strategy](../../docs/adr/0009-tracking-evaluation.md)

## Scope summary

Phase 2 expands tracker evaluation to real-world motion diversity and larger multi-camera scale
with end-to-end coverage. Seven epic items merged with validated technical debt into 8 stories.

Technical-debt validation (from `old-task-list.txt` vs. current code):

| Debt item | Verdict |
|-----------|---------|
| `process_inputs`/`process_tracker_outputs` use iterators, not file paths | Valid → S2 |
| Remove `set_camera_fps`, fold into `set_cameras` | Valid → S3 |
| Move `create_motchallenge_seqinfo` into trackeval evaluator | Valid → S3 |
| `MotChallenge3DPoint._load_raw_file` column indices (conf/class/visibility) — CoPilot [#2](https://github.com/open-edge-platform/scenescape/pull/987#discussion_r2805832131), [#3](https://github.com/open-edge-platform/scenescape/pull/987#discussion_r2805832105) | Valid, real bug → S2 |
| jsonschema pipeline-config validation (manual today) — CoPilot [suggestion](https://github.com/open-edge-platform/scenescape/pull/987#discussion_r2812244426) | Valid → S3 |
| `write_jsonl` output named `inputs.json` not `.jsonl` | Valid, minor → S3 |
| Design doc template + PipelineEngine method-name sync | Valid, minor → S3 |
| Configure FPS in evaluator vs. infer from timestamps | Mostly done (`set_base_fps` exists) → verify in S1 |
| Iterator exhaustion in PipelineEngine — CoPilot [#1](https://github.com/open-edge-platform/scenescape/pull/987#discussion_r2805832164) | Done (`list(...)` materialization) |
| Pluggable similarity scoring | Duplicate of epic item 6 → S6 |

## Priorities & dependencies

- **P1 (foundational):** S1, S2, S3, S4
- **P2 (core features):** S5, S6
- **P3 (extending reach):** S7, S8

```mermaid
graph LR
  S1[S1 GT timestamps] --> S5[S5 I-24 dataset]
  S1 --> S7[S7 No-GT qualitative]
  S2[S2 File-based I/O + bugfix] --> S3[S3 Config/API/doc hygiene]
  S2 --> S4[S4 WILDTRACK analysis]
  S2 --> S6[S6 Pluggable similarity]
  S2 --> S7
  S2 --> S8[S8 End-to-end video]
  S4 --> S8
```

## Stories

### S1 — Adopt canonical timestamp-based ground truth `[P1]`
Replace frame-number-indexed ground truth with a canonical format keyed on absolute timestamps
across datasets, harnesses and evaluators. Frame-based datasets convert frames→absolute time
internally. Work exists on branch `tracker-eval-gt-use-timestamps`; this story finalizes, hardens
and merges it.

**Acceptance criteria:**
- Canonical GT + tracker-output records carry absolute timestamps; no evaluator relies on frame indices as identity.
- Frame-based datasets convert to absolute time via configured/derived FPS; conversion unit-tested.
- WILDTRACK and Unity datasets pass evaluation end-to-end on the new format.
- Design doc + READMEs updated; existing tests green.

### S2 — Tech-debt: file-based I/O contract + shared evaluator code `[P1]`
Align intermediate artifacts on files (not in-memory iterators) and unify duplicated logic across
harnesses/evaluators. Fold in correctness fixes: `MotChallenge3DPoint._load_raw_file` column
indices, and improved resolution of multiple tracker frames into a single GT frame.

**Reference — CoPilot review comments (PR #987):**
- [#2 conf/`zero_marked` read from wrong column](https://github.com/open-edge-platform/scenescape/pull/987#discussion_r2805832131)
- [#3 class parsed from visibility column](https://github.com/open-edge-platform/scenescape/pull/987#discussion_r2805832105)

**Acceptance criteria:**
- `TrackerHarness.process_inputs` returns a path to a canonical tracker-output file; all harnesses updated.
- `TrackerEvaluator.process_tracker_outputs` accepts paths; all evaluators updated.
- Pipeline stores tracker-output + GT files under `<output>/tracker/`.
- `MotChallenge3DPoint` reads confidence/class/visibility from correct columns; regression test proves correct CLEAR/HOTA when conf/class differ.
- Common conversion/loading helpers deduplicated into shared utils; design doc + READMEs + docstrings updated.

### S3 — Config validation, FPS API cleanup & doc hygiene `[P1]`
Replace manual pipeline-config validation with jsonschema; remove `set_camera_fps` in favor of a
`camera_fps` argument on `set_cameras`; move `create_motchallenge_seqinfo` into the trackeval
evaluator; rename `write_jsonl` outputs to `*.jsonl`; align design doc to template and sync method names.

**Reference — CoPilot review comment (PR #987):** [jsonschema config validation suggestion](https://github.com/open-edge-platform/scenescape/pull/987#discussion_r2812244426)

**Acceptance criteria:**
- Pipeline YAML validated against a JSON schema with actionable error messages; invalid configs rejected.
- `set_camera_fps` removed; `set_cameras(..., camera_fps=...)` supported; FPS optional when derivable from timestamps.
- `create_motchallenge_seqinfo` lives in the trackeval evaluator; JSONL files use `.jsonl` extension.
- Design doc matches template; method names consistent across doc and code.

### S4 — Investigate WILDTRACK result differences across trackers `[P1]`
Analyze why evaluation metrics differ between tracker implementations on the already-integrated
WILDTRACK dataset and document root causes (association, projection, timing, config).

**Acceptance criteria:**
- Reproducible comparison across tracker variants (controller immediate, controller time-chunked, tracker service) on WILDTRACK.
- Written analysis explaining metric deltas with evidence (per-metric breakdown + ≥1 qualitative case).
- Findings captured under `docs/` (or evaluation README) with actionable follow-ups.

### S5 — Adopt a real vehicle dataset (I-24) `[P2]`
Integrate a real vehicle dataset (e.g. I-24) to validate higher-speed motion, large-footprint
objects and vehicle dynamics. Includes a data-acquisition/access spike before integration.

**Acceptance criteria:**
- Spike documents dataset access, licensing and format; go/no-go recorded (with fallback dataset if I-24 blocked).
- A `TrackingDataset` implementation loads the vehicle dataset into canonical format (timestamps, scene/camera config, GT).
- Evaluation pipeline runs end-to-end and produces HOTA/MOTA/IDF1 plus diagnostic metrics.
- Dataset README + config example added.

### S6 — Pluggable similarity scoring `[P2]`
Make the similarity/association score pluggable (currently Euclidean distance) and add at least one
new scorer (e.g. 2D IoU projected to the scene), with user documentation.

**Acceptance criteria:**
- A similarity-scorer interface selectable via pipeline config; Euclidean distance refactored behind it.
- ≥1 additional scorer implemented and unit-tested.
- User docs explain available scorers, config and trade-offs; design doc updated.

### S7 — Qualitative evaluation without ground truth `[P3]`
Allow the pipeline to run on demo datasets lacking ground truth so tracking quality can be compared
across trackers qualitatively. Evaluation runs on tracker outputs directly, so no GT format
conversions are needed (depends on S1).

**Acceptance criteria:**
- Pipeline runs to completion with no GT configured (no crash on missing GT).
- GT-independent outputs produced (e.g. jitter/jerk, track counts/continuity, side-by-side summary) enabling cross-tracker comparison.
- Documented workflow + example config on a demo dataset.

### S8 — End-to-end evaluation from camera video (design + prototype) `[P3]`
Design end-to-end evaluation starting from raw camera video through the upstream analytics pipeline
to cover vector-enhanced tracking and re-identification; deliver a design plus a minimal prototype.

**Acceptance criteria:**
- Design document covering video-in → analytics → tracker → evaluation data flow, including reID/vector handling and metric strategy.
- Minimal prototype demonstrates the flow on one short clip (may be scoped/mocked at boundaries).
- Gaps, risks and follow-up work explicitly listed.
