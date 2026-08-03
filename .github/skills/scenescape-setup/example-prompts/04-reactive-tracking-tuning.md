<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Reactive tracking-quality tuning after deployment

Shows that tuning questions are only asked **after** the user reports a problem with an already
running deployment, never proactively during initial Step 1 gathering.

## Prompt

```text
The SceneScape deployment in ~/deployments/warehouse-demo is up, but tracked people keep
disappearing and getting new IDs whenever they walk behind a shelf. Can you fix this?
```

## Expected agent behavior

1. Recognizes this as a post-deployment tracking-quality complaint (IDs changing during
   occlusion), not an initial deployment request.
2. Opens [tuning-tracker.md](../references/tuning-tracker.md) (not `tuning-reid.md` — no
   cross-camera Re-ID symptom was reported) and asks only its questionnaire.
3. Recommends raising `non_measurement_time_dynamic_s` (and possibly
   `suspended_track_timeout_secs`) above the shipped defaults, edits
   `<deploy_dir>/controller/tracker-config.json`, and restarts just the `scene` service
   (`docker compose up -d --force-recreate scene`) rather than redeploying from scratch.
