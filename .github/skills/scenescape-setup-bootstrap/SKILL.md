---
name: scenescape-setup-bootstrap
description: >
  SceneScape bootstrap phase (steps 6–8): configs, RTSP/pipeline validation, full stack.
  Requires user-provided streams, camera_ids, and scene_name from Step 1.
argument-hint: "<deploy_dir> — gather user inputs first unless deploy-inputs.json exists"
---

# SceneScape Setup — Bootstrap (steps 6–8)

Parent: [scenescape-setup](../scenescape-setup/SKILL.md).

## Step 1 first

On a new deploy, ask the user for `streams`, `camera_ids`, and `scene_name`. Do not assume
simulator defaults. Write `deploy-inputs.json` via `deploy_inputs.py write` or pass the same
values to the orchestrator.

## Run

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --streams <user_rtsp_url> [...] \
  --camera-ids <user_id> [...] \
  --scene-name <user_scene_name> \
  --phase bootstrap
```

Resume: `--deploy-dir` + `--skill-dir` only (loads `deploy-inputs.json`).

## On failure

[runtime-verification.md](../scenescape-setup/references/runtime-verification.md)
