<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Tuning tracker-config.json for a use case

Turns a plain-language description of a deployment's use case into concrete
`tracker-config.json` values (motion/timing behavior — publish delay, dead-track cleanup,
time-chunking rate). Read this when the user wants tracking behavior tuned to their scenario
(crowding, occlusion, camera overlap) instead of the shipped defaults. For Re-ID / cross-camera
matching tuning, see [tuning-reid.md](./tuning-reid.md) instead.

Source of truth for parameter semantics:
`docs/user-guide/microservices/controller/how-to-configure-tracker.md` in the SceneScape repo.
Where this doc gives a recommended value instead of a hard rule, it says so — the upstream docs
themselves note that time-based parameters should be "experimentally verified" for a given
deployment.

## When to run the questionnaire

Ask these questions once, right after Step 1 (inputs are gathered) and before Step 6 (bootstrap)
runs — but only if the user's request mentions tuning, or if their use-case description in Step 1
already implies non-default conditions (e.g. "crowded lobby", "vehicles in a parking lot"). If the
user just wants a quick demo/default deployment, skip this section entirely and let
`bootstrap_deploy.py` copy the shipped defaults unmodified.

## Questionnaire

| #   | Question                                                                                                        | Parameters affected                                                                               |
| --- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| 1   | What is the highest FPS among all cameras in this deployment?                                                   | `time_chunking_rate_fps`                                                                          |
| 2   | Do camera fields of view overlap? If so, how many cameras typically cover the same area?                        | `time_chunking_rate_fps` (indirectly), noted as an "experiment" variable                          |
| 3   | Are the tracked objects mostly moving (people, vehicles) or mostly static (parked/idle)?                        | `non_measurement_time_dynamic_s`, `non_measurement_time_static_s`                                 |
| 4   | How frequent/long are occlusions (columns, shelving, crowd density) expected to be?                             | `non_measurement_time_dynamic_s`, `non_measurement_time_static_s`, `suspended_track_timeout_secs` |
| 5   | Is it acceptable for a tracked object to briefly flicker in/out of the UI, or must it be stable before showing? | `max_unreliable_time_s`                                                                           |

## Parameter reference

| Parameter                        | Default | Meaning                                                                                                                                                                                                         |
| -------------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `max_unreliable_time_s`          | 1.0     | Time to wait before publishing a tracked object to the web UI/MQTT.                                                                                                                                             |
| `non_measurement_time_dynamic_s` | 0.8     | Time to wait before deleting a dead track that was moving (non-zero velocity) when lost.                                                                                                                        |
| `non_measurement_time_static_s`  | 1.6     | Time to wait before deleting a dead track that was stationary when lost.                                                                                                                                        |
| `time_chunking_enabled`          | true    | Batches detections into fixed-rate time chunks instead of processing every frame immediately.                                                                                                                   |
| `time_chunking_rate_fps`         | 10      | Tracker processing rate (Hz). Rule of thumb: set to the **highest** camera FPS in the deployment.                                                                                                               |
| `suspended_track_timeout_secs`   | 60.0    | Upper bound on how long a suspended (temporarily lost, retained for re-tracking) track is kept before final cleanup — relevant when a long occlusion or camera hand-off might later resolve to the same object. |

## Recommendation logic

Apply these adjustments relative to the shipped defaults, based on the questionnaire answers.
These are starting points, not guarantees — the upstream tracker docs explicitly recommend
experimentally verifying time-based parameters for a specific deployment.

1. **Q1/Q2 (FPS + overlap) →** set `time_chunking_rate_fps` to the highest camera FPS reported in
   Q1. If cameras overlap heavily (Q2), keep an eye on tracker CPU load — the how-to guide notes
   time-chunking rate can be lowered below the highest FPS to trade accuracy for performance, but
   only do so if the user reports/expects a CPU bottleneck.

2. **Q3/Q4 (dynamics + occlusion) →**
   - Mostly static objects with rare occlusion: keep or slightly raise
     `non_measurement_time_static_s` (default `1.6`) relative to `non_measurement_time_dynamic_s`
     — static tracks that vanish are more likely a transient detection gap than a real removal.
   - Mostly dynamic objects with frequent/long occlusion (crowds, columns, shelving): raise
     `non_measurement_time_dynamic_s` above the `0.8` default (e.g. `1.5`–`2.5`) so a person
     briefly hidden behind an obstacle isn't deleted and re-assigned a new ID. Raising this too
     far increases the chance of merging two different objects that pass through the same spot.
   - Frequent long occlusions or expected camera hand-offs: raise `suspended_track_timeout_secs`
     above the `60.0` default so a track has more time to be reconciled instead of purged.

3. **Q5 (UI stability vs. flicker tolerance) →** lower `max_unreliable_time_s` below `1.0` for
   faster on-screen appearance (demo/kiosk use cases where flicker is acceptable); raise it above
   `1.0` when a stable, confirmed track matters more than speed (e.g. security/analytics
   dashboards).

## How to apply the tuned values

The shipped `assets/tracker-config.json` is copied unmodified into `<deploy_dir>/controller/` by
`bootstrap_deploy.py` in step 6 (see [pipeline-config.md](./pipeline-config.md) for how step 6
fits into bootstrap). Edit the **copy** in `<deploy_dir>/controller/`, not the skill's `assets/`
original:

```bash
# After step 6 (bootstrap_deploy.py) has run, before step 8 (docker compose up):
$EDITOR <deploy_dir>/controller/tracker-config.json
```

The file is mounted into the `scene` container as a Docker config (see
`docker-compose-template.md`) and is only read at container start — editing it before step 8's
first `docker compose up` is sufficient. If the stack is already running, restart just the `scene`
service to pick up the change: `docker compose up -d --force-recreate scene`.
