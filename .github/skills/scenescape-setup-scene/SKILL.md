---
name: scenescape-setup-scene
description: >
  SceneScape scene phase (steps 11–13): reconstruction, finalize with user scene_name,
  tracking verification.
argument-hint: "<deploy_dir> — calibrate must be complete"
---

# SceneScape Setup — Scene (steps 11–13)

Parent: [scenescape-setup](../scenescape-setup/SKILL.md). Uses `scene_name` and `camera_ids`
from `deploy-inputs.json`.

## Run

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --phase scene
```

Reconstruction creates/finalizes the scene named in `deploy-inputs.json`.

## On failure

[reconstruction.md](../scenescape-setup/references/reconstruction.md),
[verify-tracking.md](../scenescape-setup/references/verify-tracking.md)
