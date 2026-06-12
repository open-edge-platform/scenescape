---
name: scenescape-setup-calibrate
description: >
  SceneScape calibrate phase (steps 9–10): calibration MQTT gate and mapping health.
  Uses camera IDs from deploy-inputs.json.
argument-hint: "<deploy_dir> — bootstrap must be complete"
---

# SceneScape Setup — Calibrate (steps 9–10)

Parent: [scenescape-setup](../scenescape-setup/SKILL.md). Requires bootstrap complete and
`deploy-inputs.json` with the user's camera IDs.

## Run

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --phase calibrate
```

Omit streams/camera IDs when resuming — loaded from `deploy-inputs.json`.

## On failure

[runtime-verification.md](../scenescape-setup/references/runtime-verification.md)
