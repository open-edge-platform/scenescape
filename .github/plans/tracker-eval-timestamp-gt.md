<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Timestamp-based ground truth for tracker evaluation

## Requirement

- Ground truth (GT) must use absolute timestamps, not frame numbers.
- Datasets that only provide frame-based timestamps must be auto-converted to absolute time.
- Change canonical GT format from MOTChallenge 3D CSV to the tracker-output canonical
  format (JSONL, `scene-data`-style frames with absolute ISO timestamps).
- Track vs GT matching must be based on timestamps.
- Keep it simple, no regression. Refactor duplicated evaluator code into shared helpers.

## Approved decisions

1. GT JSONL is translation-only (+ `id`, `category`); no synthesized velocity/size/rotation.
2. Matching uses **shared-reference frame quantization**: map every absolute timestamp
   (GT and tracker) to an integer frame index using a common reference epoch
   `t0 = min(first_gt_ts, first_tracker_ts)` and `fps`. This realizes timestamp-based
   matching while staying compatible with TrackEval (which requires integer frames).
3. Keep `set_base_fps`/`camera_fps` as-is (still needed for quantization + TrackEval).

## Key facts (verified)

- Source GT `tests/system/metric/{unity,wildtrack}_dataset/gtLoc.json` already contain
  absolute ISO timestamps + `objects` grouped by category. Current `get_ground_truth()`
  discards timestamps and assigns sequential 1..N frame numbers.
- Root cause fixed: tracker frames indexed from tracker `t0`; GT numbered sequentially in
  file order → desync when tracker drops frames. Shared reference removes the desync.
- TrackEval library requires integer frame indices (`MotChallenge3DPoint`).
- Evaluators & current matching keys:
  - TrackEvalEvaluator: tracker→CSV via `convert_canonical_to_motchallenge_csv`, GT CSV
    copied; frame numbers.
  - DiagnosticEvaluator: `{int_id:{frame:(x,y)}}`, bipartite on frame overlap.
  - CameraAccuracyEvaluator: `{(cam,obj):{frame:(x,y)}}`, per-pair frame overlap.
  - JitterEvaluator: tracker keyed by real timestamps; GT frame→synthetic epoch timestamp.
- `pipeline_engine.evaluate()` passes `dataset.get_ground_truth()` path to every evaluator.

## Shared module: `utils/timeline.py` (new)

- `parse_timestamp(ts) -> datetime`
- `deduplicate_frames_by_timestamp(frames) -> list`
- `compute_fps(timestamps, base_fps) -> float`
- `timestamp_to_frame(ts, reference, fps) -> int` (1-indexed)
- `reference_timestamp(*frame_lists) -> datetime` (min of first timestamps)
- `build_frame_indexed_tracks(frames, reference, fps, id_fn, pos_fn) -> {key:{frame:pos}}`
- `normalize_histories_to_fps(histories, fps) -> histories` (epoch+idx/fps grid; jitter)

`convert_canonical_to_motchallenge_csv` extended with `reference_timestamp=None`
(defaults to first tracker timestamp) so GT + tracker share one timeline.

GT is read with existing `stream_jsonl` (GT == tracker-output canonical format).

## Steps (commit after each)

1. Shared helpers: add `utils/timeline.py`; extend
   `convert_canonical_to_motchallenge_csv` with `reference_timestamp`; add unit tests.
2. Datasets: rewrite `UnityDataset.get_ground_truth()` and
   `WildtrackDataset.get_ground_truth()` to emit `ground_truth.jsonl` (flattened objects,
   absolute timestamps, keep category filter + Unity sampling stride). Update
   `base/tracking_dataset.py` docstring. Update dataset tests.
3. TrackEvalEvaluator: read GT JSONL, compute shared reference, convert both GT+tracker to
   MOTChallenge with shared reference/fps. Update tests.
4. DiagnosticEvaluator: shared-reference frame index for tracker + GT (JSONL); use shared
   helpers. Update tests.
5. CameraAccuracyEvaluator: shared-reference frame index + JSONL GT; shared helpers.
   Update tests.
6. JitterEvaluator: read GT JSONL with real timestamps; refactor fps-grid normalization to
   shared helper. Update tests.
7. Docs: README GT format section, Available Evaluators wording, Agents.md.
8. Verification + regression.

## Verification

- Unit: `pytest . -v -m "not integration"` (from `tools/tracker/evaluation`, `.venv`).
- Integration: `pytest . -v -m integration` (Docker images required).
- Full pipeline CLI: `python pipeline_engine.py pipeline_configs/metric_test_evaluation.yaml`.
- Black-box: `python -m run_black_box_evaluation` and `--dataset wildtrack`.
- Regression: capture baseline metrics on `main` first; compare HOTA/MOTA/IDF1/DIST_T
  within tolerance (non-deterministic). Expect equal-or-better; improved when frames drop.

## Critical opens / risks

- GT `id` namespace differs from tracker; TrackEval associates independently, so GT ids only
  need internal consistency (fresh remap is fine).
- Tracker output timestamps must lie on the same cadence as GT (existing frame-rate
  assumption). Shared-reference quantization tolerates small float noise.
- Unity `sampling_stride` GT subsampling retained to avoid inflating TrackEval FN counts.
