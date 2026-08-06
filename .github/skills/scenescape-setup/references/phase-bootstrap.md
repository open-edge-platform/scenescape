<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Running Bootstrap Alone (steps 6–8)

Use this when the user asks to run, redo, or resume **only** the bootstrap phase (configs,
RTSP/pipeline validation, full stack) for a deployment that already has (or is about to get)
`deploy-inputs.json` — not a full end-to-end deploy.

Bootstrap (step 6) always runs `adapt_pipeline_config.py`. When
`pipeline_customization_prompt` is set in `deploy-inputs.json`, the agent must first follow
[dlstreamer-coding-agent](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent)
and write `pipeline-customization/result.json`; bootstrap then runs `configure_pipeline.py`
to merge it (see [pipeline-customization.md](./pipeline-customization.md)).

## Prerequisite

On a new deploy, Step 1 (gather `streams`, `camera_ids`, `scene_name`) must run first — do not
assume simulator defaults. Write `deploy-inputs.json` via `deploy_inputs.py write` or pass the
same values inline below.

## Safety rules

- This phase generates TLS secrets and brings up containers for the first time (`docker compose
up -d video-analytics`, then the full stack). Show the command before running it.
- Never interpolate raw `streams`/`camera_ids`/`scene_name` into ad hoc shell commands; pass them
  through `deploy_inputs.py` / the orchestrator only.
- Restrict file writes to `<deploy_dir>` and `$SKILL_DIR`.

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

This phase can take several minutes (Docker pulls, model downloads, RTSP warmup) — launch it in
an async terminal and poll for completion rather than blocking.

## Reference Lookup

| Reference                                            | Purpose                                           |
| ---------------------------------------------------- | ------------------------------------------------- |
| [pipeline-config.md](./pipeline-config.md)           | How per-camera pipelines are generated (step 6)   |
| [pipeline-customization.md](./pipeline-customization.md) | Optional external-agent customization inside step 6 |
| [mosquitto-config.md](./mosquitto-config.md)         | Broker TLS listener layout (step 6)               |
| [command-templates.md](./command-templates.md)       | RTSP gate check / MQTT pub-sub commands (step 7)  |
| [runtime-verification.md](./runtime-verification.md) | RTSP/service-health failure diagnosis (steps 7–8) |
