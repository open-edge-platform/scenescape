---
name: scenescape-setup
description: >
  Deploy a working Intel® SceneScape installation from scratch (outside the repo). Gathers
  user-provided streams, camera IDs, and scene name, then runs bootstrap through tracking
  verification via scripts/deploy_scenescape.sh.
argument-hint: "<deploy_dir> — always gather streams, camera_ids, scene_name from the user first"
---

# SceneScape End-to-End Setup

Host needs **Docker**, **docker-compose**, and **Python 3.10+** with `requests`.

## Agent guardrails

- **Step 1 is mandatory on a new deploy** — ask the user for `streams`, `camera_ids`, and
  `scene_name`. Do not assume values from prior sessions, sample data, or running containers.
- **Prefer the orchestrator** after inputs are confirmed; read `deploy.log` only on failure.
- **Do not read** `docker-compose-template.md` or `sample_data/` unless troubleshooting a
  template bug. Pipeline generation is defined in `pipeline-config.md`.
- **Do not** dump raw `docker compose logs`; use `check_service_health.py` and focused log filters.
- **Resume** with `--deploy-dir` only when `deploy-inputs.json` exists; use `--fresh` when
  cameras or streams change.
- Load troubleshooting references only when a step fails.
- **Never** assign `SKILL_DIR` inline with `bash` on the same command (`SKILL_DIR=x bash "$SKILL_DIR/..."` silently fails because the variable is not yet expanded). Always set `export SKILL_DIR=...` on its own line first.

## Step 0 — Bootstrap skill-dir

Resolve `SKILL_DIR` before any other step. Use the **first matching** strategy below:

**A. Scripts already on disk** (scenescape repo is checked out locally):

```bash
export SKILL_DIR=<path-to-scenescape-checkout>/.github/skills/scenescape-setup
```

**B. Extract from git** (no full checkout needed — fast, leaves no branch state):

```bash
# Find any local scenescape clone
SCENESCAPE_REPO=$(find ~ -maxdepth 5 -type d -name scenescape 2>/dev/null | head -1)
# Archive just the skill directory from the feature branch
git -C "$SCENESCAPE_REPO" fetch origin feature/sscape-app-skill
mkdir -p /tmp/scenescape-skill
git -C "$SCENESCAPE_REPO" archive origin/feature/sscape-app-skill \
  -- .github/skills/scenescape-setup | tar -x -C /tmp/scenescape-skill
export SKILL_DIR=/tmp/scenescape-skill/.github/skills/scenescape-setup
```

Verify: `ls "$SKILL_DIR/scripts/deploy_scenescape.sh"` must succeed before continuing.

## Step 1 — Gather inputs (required)

Ask the user for every new deployment:

| Input        | Rules                                                  |
| ------------ | ------------------------------------------------------ |
| `deploy_dir` | Writable directory for generated files                 |
| `streams`    | One RTSP/RTSPS URL per camera, user-provided, in order |
| `camera_ids` | Unique IDs (no `/`), same order as `streams`           |
| `scene_name` | Human-readable scene name chosen by the user           |

Validate: `len(streams) == len(camera_ids)`, ≥1 camera, valid RTSP URLs.

Persist before automation:

Use `python3` by default. Do not substitute a virtualenv interpreter path unless
you have confirmed that path exists on disk.

```bash
python3 <skill-dir>/scripts/deploy_inputs.py write \
  --deploy-dir <deploy_dir> \
  --scene-name <scene_name> \
  --camera-ids <id> [<id> ...] \
  --streams <rtsp_url> [<rtsp_url> ...] \
  --skill-dir <skill-dir>
```

Writes `<deploy_dir>/deploy-inputs.json` — the source of truth for all later steps.
Pipeline adaptation reads RTSP URLs from the downloaded template entry per camera; it does not
hardcode simulator hostnames or camera names.

## Orchestrator (steps 2–13)

After Step 1, run:

```bash
export SKILL_DIR=<path-to-scenescape>/.github/skills/scenescape-setup

bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --streams <rtsp_url> [...] \
  --camera-ids <id> [...] \
  --scene-name <scene_name>
```

**Resume** (inputs loaded from `deploy-inputs.json` when omitted):

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR"
```

| Flag                                       | Purpose                                                               |
| ------------------------------------------ | --------------------------------------------------------------------- |
| `--phase all\|bootstrap\|calibrate\|scene` | Limit steps (default `all`)                                           |
| `--resume`                                 | Continue from `.deploy-state.json` (default)                          |
| `--fresh`                                  | Clear checkpoint and `deploy-inputs.json`; requires new Step 1 inputs |

**Pass:** `DEPLOY COMPLETE` with `scene_uid`. **Fail:** `deploy.log` + step reference below.

### Step map

| Step  | Action                                                                | Pass                              |
| ----- | --------------------------------------------------------------------- | --------------------------------- |
| 1     | `deploy_inputs.py write`                                              | `deploy-inputs.json` valid        |
| 6     | `bootstrap_deploy.py --from-deploy-inputs`                            | secrets, compose, pipeline config |
| 7     | warmup, `verify_rtsp.sh`, `check_service_health.py` (video-analytics) | RTSP + pipelines                  |
| 8     | full stack `up`                                                       | core services running             |
| 9     | `capture_calibration_frames.py`                                       | JPEG per **user** camera ID       |
| 10    | `check_service_health.py` (mapping endpoint + model_loaded)           | mapping healthy                   |
| 11–12 | `reconstruct_and_finalize.py --scene-name`                            | scene UID                         |
| 13    | `verify_tracking.sh`                                                  | objects on regulated topic        |

Checkpoints: `.deploy-state.json` (progress), `deploy-inputs.json` (user inputs).

## Phased sub-skills

| Skill                                                                | Phase       |
| -------------------------------------------------------------------- | ----------- |
| [scenescape-setup-bootstrap](../scenescape-setup-bootstrap/SKILL.md) | steps 6–8   |
| [scenescape-setup-calibrate](../scenescape-setup-calibrate/SKILL.md) | steps 9–10  |
| [scenescape-setup-scene](../scenescape-setup-scene/SKILL.md)         | steps 11–13 |

Each sub-skill still requires user inputs (or `deploy-inputs.json` on resume).

## On failure

| Step  | Reference                                                       |
| ----- | --------------------------------------------------------------- |
| 7, 9  | [runtime-verification.md](./references/runtime-verification.md) |
| 11–12 | [reconstruction.md](./references/reconstruction.md)             |
| 13    | [verify-tracking.md](./references/verify-tracking.md)           |

[pipeline-config.md](./references/pipeline-config.md) — how template adaptation works.

## Prerequisites

- GitHub access (sparse checkout of `dlstreamer-pipeline-server`)
- Proxy: `http_proxy` / `https_proxy` / `no_proxy`; RTSP Docker hostnames appended automatically
- TLS certs generated in step 6; superuser password in `secrets/supass`
