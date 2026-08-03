<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Running Calibrate Alone (steps 9–10)

Use this when the user asks to (re)run **only** calibration (calibration frames + mapping health)
for a deployment where bootstrap (steps 6–8) is already complete.

## Prerequisite

Bootstrap must be complete for this `deploy_dir` and `deploy-inputs.json` must contain the
user's camera IDs.

## Safety rules

- Do not re-run bootstrap or bring up unrelated services from this phase; it only captures
  calibration frames and checks mapping health.
- Restrict file writes to `<deploy_dir>/calibration-frames` and `<deploy_dir>/.deploy-state.json`.

## Run

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --phase calibrate
```

Omit streams/camera IDs — loaded from `deploy-inputs.json`.

Mapping health checks (step 10) can take up to a few minutes to become ready; launch in an async
terminal and poll rather than blocking if run standalone.

## Reference Lookup

| Reference                                            | Purpose                                                           |
| ---------------------------------------------------- | ----------------------------------------------------------------- |
| [runtime-verification.md](./runtime-verification.md) | Calibration-frame / mapping-health failure diagnosis (steps 9–10) |
