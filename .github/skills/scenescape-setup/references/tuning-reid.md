<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Tuning reid-config.json for a use case

Turns a plain-language description of a deployment's use case into concrete `reid-config.json`
values (re-identification behavior — similarity matching, feature accumulation, database
flushing). Read this when the user needs cross-camera re-identification tuned to their scenario
(scene density, subject distance/size, matching strictness) instead of the shipped defaults. For
motion/timing tuning (occlusion, dead-track cleanup, time-chunking), see
[tuning-tracker.md](./tuning-tracker.md) instead.

Source of truth for parameter semantics:
`docs/user-guide/microservices/controller/Extended-ReID.md` in the SceneScape repo.

## When to run the questionnaire

Ask these questions once, right after Step 1 (inputs are gathered) and before Step 6 (bootstrap)
runs — but only if the user's request mentions Re-ID/cross-camera tracking, or if their use-case
description in Step 1 already implies it (e.g. "re-identify people across buildings", "track the
same vehicle between non-overlapping cameras"). If the user just wants a quick demo/default
deployment, or has no cross-camera Re-ID need, skip this section entirely and let
`bootstrap_deploy.py` copy the shipped defaults unmodified.

## Questionnaire

| #   | Question                                                                                                 | Parameters affected                                                                                |
| --- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1   | Do you need to re-identify the same person/vehicle across non-overlapping cameras (cross-camera Re-ID)?  | `similarity_metric`, `similarity_threshold`, `feature_accumulation_threshold`                      |
| 2   | How close/large do subjects appear in frame (near-field close-up vs. wide/high-mounted overview camera)? | `minimum_bbox_area`                                                                                |
| 3   | How many distinct people/vehicles are expected in the scene at once (sparse vs. crowded)?                | `feature_accumulation_threshold`, `VDMS_CONFIDENCE_THRESHOLD` (env var, not in `reid-config.json`) |

## Parameter reference

| Parameter                           | Default (metric-dependent)                         | Meaning                                                                                                                                                  |
| ----------------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `similarity_metric`                 | `L2` (repo default), `COSINE` (this skill's asset) | `L2` = distance, lower is better. `COSINE` = normalized vectors, higher is better, scores in `[-1, 1]`.                                                  |
| `similarity_threshold`              | `40.0` for `L2`, `0.5` for `COSINE`                | Match acceptance cutoff, interpreted per the metric above (below for `L2`, above for `COSINE`).                                                          |
| `feature_accumulation_threshold`    | 12                                                 | Minimum number of quality embeddings collected before a similarity query is even attempted. Higher = more confident matches, slower first-match latency. |
| `minimum_bbox_area`                 | 5000 (pixels²)                                     | Minimum detection bounding-box area before it contributes an embedding. Too high for a far/high-mounted camera silently disables Re-ID for that camera.  |
| `stale_feature_timeout_secs`        | 5.0                                                | How long embeddings accumulate in memory before being flushed to VDMS for persistence.                                                                   |
| `stale_feature_check_interval_secs` | 1.0                                                | How often the background timer checks for stale features to flush.                                                                                       |
| `feature_slice_size`                | 10                                                 | Persist every Nth accumulated embedding to VDMS (reduces database growth).                                                                               |

`VDMS_CONFIDENCE_THRESHOLD` (default `0.8`) is a controller **environment variable**, not a
`reid-config.json` field — it controls how strict TIER 1 metadata filtering is (age/gender/etc.)
before TIER 2 vector similarity runs. Lower it (e.g. `0.7`) for more aggressive metadata
filtering, raise it (e.g. `0.9`) to rely more on vector similarity alone.

## Recommendation logic

Apply these adjustments relative to the shipped defaults, based on the questionnaire answers.
These are starting points, not guarantees.

1. **Q1 (cross-camera Re-ID needed) →**
   - If **not** needed: leave Re-ID at its shipped defaults; no changes required.
   - If needed: keep `similarity_metric: "COSINE"` (already the shipped asset default) since it
     gives bounded, normalized scores that are easier to reason about across cameras. Consider
     raising `feature_accumulation_threshold` above `12` for higher-confidence cross-camera
     matches in crowded scenes (trade-off: slower first match).

2. **Q2 (subject size in frame) →** lower `minimum_bbox_area` below `5000` for wide/high-mounted
   overview cameras where subjects appear smaller in pixels; the repo default assumes a
   moderate-distance retail-style camera. Do not lower it so far that partial/edge detections
   start contributing noisy embeddings.

3. **Q3 (scene density) →** for crowded scenes, prefer raising `feature_accumulation_threshold`
   (more confidence before matching) over lowering `VDMS_CONFIDENCE_THRESHOLD`, since the latter
   affects TIER 1 metadata filtering strictness across the whole controller, not just this
   scene's tracks.

## How to apply the tuned values

The shipped `assets/reid-config.json` is copied unmodified into `<deploy_dir>/controller/` by
`bootstrap_deploy.py` in step 6 (see [pipeline-config.md](./pipeline-config.md) for how step 6
fits into bootstrap). Edit the **copy** in `<deploy_dir>/controller/`, not the skill's `assets/`
original:

```bash
# After step 6 (bootstrap_deploy.py) has run, before step 8 (docker compose up):
$EDITOR <deploy_dir>/controller/reid-config.json
```

The file is mounted into the `scene` container as a Docker config (see
`docker-compose-template.md`) and is only read at container start — editing it before step 8's
first `docker compose up` is sufficient. If the stack is already running, restart just the `scene`
service to pick up the change: `docker compose up -d --force-recreate scene`.

`VDMS_CONFIDENCE_THRESHOLD` is set via the controller's environment (`docker-compose.yml` or
`.env`), not a JSON file — only touch it if Q3's answer indicates crowded, metadata-heavy
scenarios need adjustment.
