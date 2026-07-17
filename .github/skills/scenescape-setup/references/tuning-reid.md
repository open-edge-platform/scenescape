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

Reactive only — per [SKILL.md](../SKILL.md#tuning-trackerre-id-behavior-reactive-only), do **not**
ask these questions upfront during Step 1. Always deploy first with the shipped
`reid-config.json` defaults unmodified. Only run this questionnaire **after** a deployment is
running and the user reports that re-identification across cameras is missing or matching the
wrong person.

## Questionnaire

| #   | Question                                                                                                 | Parameters affected                                                                                |
| --- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1   | Do you need to re-identify the same person/vehicle across non-overlapping cameras (cross-camera Re-ID)?  | `similarity_metric`, `similarity_threshold`, `feature_accumulation_threshold`                      |
| 2   | How close/large do subjects appear in frame (near-field close-up vs. wide/high-mounted overview camera)? | `minimum_bbox_area`                                                                                |
| 3   | How many distinct people/vehicles are expected in the scene at once (sparse vs. crowded)?                | `feature_accumulation_threshold`, `VDMS_CONFIDENCE_THRESHOLD` (env var, not in `reid-config.json`) |

## Parameter reference

| Parameter                           | Default (metric-dependent)          | Meaning                                                                                                                                                  |
| ----------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `similarity_metric`                 | `COSINE`                            | `COSINE` = normalized vectors, higher is better, scores in `[-1, 1]`. `L2` = distance, lower is better, remains available as an alternative.             |
| `similarity_threshold`              | `0.5` for `COSINE`, `40.0` for `L2` | Match acceptance cutoff, interpreted per the metric above (above for `COSINE`, below for `L2`).                                                          |
| `feature_accumulation_threshold`    | 12                                  | Minimum number of quality embeddings collected before a similarity query is even attempted. Higher = more confident matches, slower first-match latency. |
| `minimum_bbox_area`                 | 5000 (pixels²)                      | Minimum detection bounding-box area before it contributes an embedding. Too high for a far/high-mounted camera silently disables Re-ID for that camera.  |
| `stale_feature_timeout_secs`        | 5.0                                 | How long embeddings accumulate in memory before being flushed to VDMS for persistence.                                                                   |
| `stale_feature_check_interval_secs` | 1.0                                 | How often the background timer checks for stale features to flush.                                                                                       |
| `feature_slice_size`                | 10                                  | Persist every Nth accumulated embedding to VDMS (reduces database growth).                                                                               |

`VDMS_CONFIDENCE_THRESHOLD` (default `0.8`) is a controller **environment variable**, not a
`reid-config.json` field — it controls how strict TIER 1 metadata filtering is (age/gender/etc.)
before TIER 2 vector similarity runs. Lower it (e.g. `0.7`) for more aggressive metadata
filtering, raise it (e.g. `0.9`) to rely more on vector similarity alone.

## Recommendation logic

Apply these adjustments relative to the shipped defaults, based on the questionnaire answers.
These are starting points, not guarantees.

1. **Q1 (cross-camera Re-ID needed) →**
   - If **not** needed: leave Re-ID at its shipped defaults; no changes required.
   - If needed: keep `similarity_metric: "COSINE"` (already the default, both in the controller
     and this skill's shipped `reid-config.json`) since it gives bounded, normalized scores that
     are easier to reason about across cameras. Consider raising `feature_accumulation_threshold`
     above `12` for higher-confidence cross-camera matches in crowded scenes (trade-off: slower
     first match).

2. **Q2 (subject size in frame) →** lower `minimum_bbox_area` below `5000` for wide/high-mounted
   overview cameras where subjects appear smaller in pixels; the repo default assumes a
   moderate-distance retail-style camera. Do not lower it so far that partial/edge detections
   start contributing noisy embeddings.

3. **Q3 (scene density) →** for crowded scenes, prefer raising `feature_accumulation_threshold`
   (more confidence before matching) over lowering `VDMS_CONFIDENCE_THRESHOLD`, since the latter
   affects TIER 1 metadata filtering strictness across the whole controller, not just this
   scene's tracks.

## How to apply the tuned values

Since tuning is reactive (see above), the deployment is normally already running when these
values are applied. Edit `<deploy_dir>/controller/reid-config.json` (the copy
`bootstrap_deploy.py` placed there in step 6 — see [pipeline-config.md](./pipeline-config.md) for
how step 6 fits into bootstrap; never edit the skill's `assets/reid-config.json` original), then
restart just the `scene` service to pick up the change:

```bash
$EDITOR <deploy_dir>/controller/reid-config.json
docker compose up -d --force-recreate scene
```

The file is mounted into the `scene` container as a Docker config (see
`docker-compose-template.md`) and is only read at container start, so the restart is required. If
tuning happens to be requested before step 8's first `docker compose up` (e.g. the user already
knew their Re-ID needs during Step 1, overriding the reactive default), editing the file at that
point is sufficient and no restart is needed yet.

`VDMS_CONFIDENCE_THRESHOLD` is set via the controller's environment (`docker-compose.yml` or
`.env`), not a JSON file — only touch it if Q3's answer indicates crowded, metadata-heavy
scenarios need adjustment.
