<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Deployment operational reference

Read this only when the user asks about generated deployment files or the web-UI handoff, or when
a bootstrap, runtime, reconstruction, or tracking-verification failure needs diagnosis. Do not
read it for a routine deploy or resume; the core skill contains those commands and criteria.

## Orchestrator

```bash
export SKILL_DIR=<path-to-scenescape>/.github/skills/scenescape-setup

bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --streams <rtsp_url> [...] \
  --camera-ids <id> [...] \
  --scene-name <scene_name>
```

To resume, omit the inputs:

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR"
```

Launch the orchestrator asynchronously. It runs bootstrap (steps 6-8), calibrate (9-10), then
scene (11-13). `--fresh` clears `.deploy-state.json` and `deploy-inputs.json`, so it requires
new Step 1 inputs and reruns all three phases.

Step 9 creates one calibration JPEG per camera ID in `calibration-frames/`. Step 13 verifies that
tracked objects are associated with more than one camera ID for a multi-camera deployment.

| Flag | Purpose |
| --- | --- |
| `--phase all\|bootstrap\|calibrate\|scene` | Limit steps; defaults to `all` |
| `--resume` | Continue from `.deploy-state.json`; default |
| `--fresh` | Clear checkpoint and inputs; requires new Step 1 inputs |

## Generated deployment layout

`<deploy_dir>` contains `deploy-inputs.json`, `.deploy-state.json`, `deploy.log`,
`docker-compose.yml`, `secrets/`, `dlstreamer-pipeline-server/`, and
`calibration-frames/`. Use `deploy-inputs.json` as the source of truth for user inputs and
`.deploy-state.json` to determine the next unfinished step.

## Phase and troubleshooting references

| Need | Reference |
| --- | --- |
| Bootstrap only | [phase-bootstrap.md](./phase-bootstrap.md) |
| Calibrate only | [phase-calibrate.md](./phase-calibrate.md) |
| Scene only | [phase-scene.md](./phase-scene.md) |
| Pipeline configuration | [pipeline-config.md](./pipeline-config.md) |
| MQTT configuration | [mosquitto-config.md](./mosquitto-config.md) |
| Compose-template failure | [docker-compose-template.md](./docker-compose-template.md) |
| RTSP or health-check failure | [runtime-verification.md](./runtime-verification.md) |
| File-backed RTSP / MediaMTX publisher | [video-file-publishing.md](./video-file-publishing.md) |
| Local video input gathering | [video-file-input.md](./video-file-input.md) |
| RTSP and MQTT commands | [command-templates.md](./command-templates.md) |
| Reconstruction failure | [reconstruction.md](./reconstruction.md) |
| Scene/camera REST inspection | [scene-and-cameras.md](./scene-and-cameras.md) |
| Tracking verification failure | [verify-tracking.md](./verify-tracking.md) |
| Blueprint, mesh, or geospatial map | [scene-map-alternatives.md](./scene-map-alternatives.md) |
| Persist AI-pipeline attributes | [attribute-persistence.md](./attribute-persistence.md) |
| Add scalar sensors | [singleton-sensors.md](./singleton-sensors.md) |
| Define object shapes | [object-library.md](./object-library.md) |
| Consume output, regions, or tripwires | [using-scene-output.md](./using-scene-output.md) |

## Assets

`bootstrap_deploy.py` copies these assets to the deployment; do not run the assets directly:
[generate_secrets.sh](../assets/generate_secrets.sh),
[openssl.cnf](../assets/openssl.cnf),
[tracker-config.json](../assets/tracker-config.json), and
[reid-config.json](../assets/reid-config.json).

## Completion handoff

After `DEPLOY COMPLETE` with a `scene_uid`, report requirements-gathering, bootstrap,
calibration, scene-and-verification, and total wall-clock times. Direct the user to
`https://localhost`, explain that the self-signed certificate must be accepted, use username
`admin`, and point them to `<deploy_dir>/secrets/supass` instead of exposing its value. Ask what
they want to do with the tracked-object data, then load the matching output-integration reference.
