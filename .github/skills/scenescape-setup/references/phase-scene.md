<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Running Scene Alone (steps 11–13)

Use this when the user asks to (re)run **only** reconstruction, finalization, or tracking
verification for a deployment where calibration (steps 9–10) is already complete.

## Prerequisite

Calibration must be complete for this `deploy_dir`. Uses `scene_name` and `camera_ids` from
`deploy-inputs.json`.

## Safety rules

- Reconstruction and finalization write into the scene named in `deploy-inputs.json`; do not
  substitute a different scene name without explicit user confirmation.
- Restrict file writes to `<deploy_dir>` and `$SKILL_DIR`.

## Run

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --phase scene
```

Reconstruction creates/finalizes the scene named in `deploy-inputs.json`.

Reconstruction and tracking verification (step 13 waits up to ~45s for camera subscriptions,
then up to ~2 minutes for regulated tracks) can take a while; launch asynchronously with
`watch_orchestrator.sh` (see [deploy-and-complete.md](./deploy-and-complete.md)) rather than blocking or asking the
user to poll. Step 13 **fails** if fewer than `len(camera_ids)` scene controller camera
subscriptions appear — see [verify-tracking.md](./verify-tracking.md).

## Reference Lookup

| Reference                                      | Purpose                                                           |
| ---------------------------------------------- | ----------------------------------------------------------------- |
| [reconstruction.md](./reconstruction.md)       | Reconstruction / finalization failure diagnosis (steps 11–12)     |
| [scene-and-cameras.md](./scene-and-cameras.md) | Manual scene/camera REST calls if reconstruction needs inspection |
| [verify-tracking.md](./verify-tracking.md)     | Tracking verification failure diagnosis (step 13)                 |
