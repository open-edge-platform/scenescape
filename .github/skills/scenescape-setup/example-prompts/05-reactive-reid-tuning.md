<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Reactive Re-ID tuning after deployment

Shows that Re-ID tuning questions are only asked **after** the user reports a cross-camera
re-identification problem with an already running deployment, never proactively during initial
Step 1 gathering.

## Prompt

```text
The SceneScape deployment in ~/deployments/retail-demo is up, but the same shopper walking from
cam1 to cam3 keeps getting a new ID instead of being recognized as the same person. Can you fix
this?
```

## Expected agent behavior

1. Recognizes this as a post-deployment cross-camera Re-ID complaint (identity not preserved
   between non-overlapping cameras), not an initial deployment request.
2. Opens [tuning-reid.md](../references/tuning-reid.md) (not `tuning-tracker.md` — the symptom is
   re-identification across cameras, not occlusion/flicker within one camera) and asks only its
   questionnaire.
3. Recommends adjustments such as raising `feature_accumulation_threshold` and/or confirming
   `similarity_metric`/`similarity_threshold` are appropriate, edits
   `<deploy_dir>/controller/reid-config.json`, and restarts just the `scene` service
   (`docker compose up -d --force-recreate scene`) rather than redeploying from scratch.
