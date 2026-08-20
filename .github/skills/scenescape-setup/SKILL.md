---
name: scenescape-setup
description: >
  Deploy a working Intel® SceneScape installation from scratch (outside the repo). Gathers
  user-provided streams, camera IDs, scene name, and mapping choice, then runs bootstrap through
  tracking verification via scripts/deploy_scenescape.sh. Also handles re-running or resuming a
  single phase of an existing deployment on request (e.g. "recalibrate", "redo scene
  reconstruction", "resume bootstrap only") via the orchestrator's --phase flag.
license: Apache-2.0
compatibility: >-
  Requires Docker, docker-compose, and Python 3.10+ with `requests` on the host. GitHub access
  for sparse checkout of dlstreamer-pipeline-server. Network access to RTSP camera streams.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, Env
metadata:
  argument-hint: "<deploy_dir> — always gather streams, camera_ids, scene_name, mapping from the user first"
---

# SceneScape End-to-End Setup

Host needs **Docker**, **docker-compose**, and **Python 3.10+** with `requests`.

## Overview

This skill deploys and resumes an Intel® SceneScape environment outside the repo, gathers the
required deployment inputs from the user, and orchestrates the bootstrap, calibration, scene
reconstruction, and verification workflow. It is intended for first-time installs, re-runs with
existing `deploy-inputs.json`, and targeted phase resumes such as `bootstrap`, `calibrate`, or
`scene` when the user only needs to repeat or continue a part of the deployment.

## Parameters / Arguments

Required runtime inputs for a fresh deployment: `deploy_dir`, `streams` (or video files),
`camera_ids`, `scene_name`, `mapping` (scene map source: `reconstruction` default, blueprint,
`.glb`/`.ply` mesh, or geospatial). When providing a `.glb` mesh with pre-calibrated cameras,
optional parameters include `--glb-file` and `--camera-json`. Optional state fields: `--phase`, `--fresh`, and the resume
flag implied by the Fast Path.

## Returns / Output

Deployment artifacts in `deploy_dir`: `deploy-inputs.json` (source of truth),
`.deploy-state.json`, orchestrator logs, calibration/reconstruction/verification outputs, and a
final `DEPLOY COMPLETE` with a `scene_uid` and deployment metrics.

## Error handling

Fail safely instead of guessing: mismatched/duplicate streams vs `camera_ids` → stop and ask for
corrected inputs; unreadable prior inputs on a camera-change fresh redeploy → ask the user to
confirm the retained set; missing local repo/docs → fall back to the canonical GitHub URL rather
than fabricating; resume/continue signal → treat `deploy-inputs.json` as existing and skip
Step 1 unless the user says the directory is wrong; a failed step → read only the matching
troubleshooting reference, no broad log dumps.

## File resolution

All scripts, references, and assets resolve relative to `$SKILL_DIR`, so the skill folder is
self-contained and portable. `docs/user-guide/...` links point at the local checkout first; if
unavailable (standalone skill copy), fall back to
`https://github.com/open-edge-platform/scenescape/blob/main/<path>` instead of guessing. Never
copy SceneScape repo docs into `references/`; reserve new references for knowledge that has no
written form elsewhere.

## Always-on rules (no exceptions)

- Before any deploy/resume/phase launch, read
  [agent-guardrails.md](./references/agent-guardrails.md).
- Every orchestrator launch also starts `watch_orchestrator.sh` on the orchestrator PID in the
  background, notifying on `RESULT=`; never ask the user to poll status.
- Never invent camera IDs/streams/scene names; never interpolate raw inputs into ad hoc shell
  one-liners; destructive actions (`--fresh`, deleting `deploy_dir`, `docker compose down -v`)
  always need explicit confirmation.
- Load only the single phase/symptom reference that matches a reported failure.

## Step 0 — Bootstrap skill-dir

Resolve `SKILL_DIR` before any other step, using the first matching strategy:

**A. Scripts already on disk** (scenescape repo is checked out locally):

```bash
export SKILL_DIR=<path-to-scenescape-checkout>/.github/skills/scenescape-setup
```

**B. Extract from git** (no full checkout needed — fast, leaves no branch state):

```bash
SCENESCAPE_REPO=$(find ~ -maxdepth 5 -type d -name scenescape 2>/dev/null | head -1)
git -C "$SCENESCAPE_REPO" fetch origin main
mkdir -p /tmp/scenescape-skill
git -C "$SCENESCAPE_REPO" archive origin/main \
  -- .github/skills/scenescape-setup | tar -x -C /tmp/scenescape-skill
export SKILL_DIR=/tmp/scenescape-skill/.github/skills/scenescape-setup
```

Verify: `ls "$SKILL_DIR/scripts/deploy_scenescape.sh"` must succeed before continuing.

## Routing

| Situation | Reference to read |
| --------- | ----------------- |
| **New deployment** (gather inputs, mapping choice, video files) | [step-1-gather-inputs.md](./references/step-1-gather-inputs.md) |
| **Resume / repeat / Fast Path** ("continue", "resume", unchanged inputs) | [fast-path.md](./references/fast-path.md) |
| **Launch** (full deploy, resume, or `--phase` orchestrator + watcher + README + handoff) | [deploy-and-complete.md](./references/deploy-and-complete.md) |
| **Single phase**: bootstrap (6–8), calibrate (9–10), scene (11–13) | [phase-bootstrap.md](./references/phase-bootstrap.md) / [phase-calibrate.md](./references/phase-calibrate.md) / [phase-scene.md](./references/phase-scene.md) |
| Tracking flickers, vanishes, or IDs change (same camera) | [tuning-tracker.md](./references/tuning-tracker.md) |
| Cross-camera Re-ID misses / wrong person | [tuning-reid.md](./references/tuning-reid.md) |
| Keep a vision attribute from resetting | [attribute-persistence.md](./references/attribute-persistence.md) |
| External non-vision sensor reading/event | [singleton-sensors.md](./references/singleton-sensors.md) |
| Expected size/shape for a class (Object Library) | [object-library.md](./references/object-library.md) |
| After successful deploy — what to build with scene output (required handoff) | [using-scene-output.md](./references/using-scene-output.md) |
| Generated-file layout / web-UI handoff / bootstrap-runtime-reconstruction diagnosis | [operational-reference.md](./references/operational-reference.md) (only for those needs — not during routine deploy) |

## Tuning tracker/Re-ID behavior (reactive only)

Do **not** ask tuning questions upfront during Step 1 — always deploy with the shipped
`tracker-config.json` / `reid-config.json` defaults first. Open the matching questionnaire only
**after** the user reports tracking/Re-ID dissatisfaction. In that first response:

1. State which reference you opened (`tuning-tracker.md` or `tuning-reid.md` — exactly one).
2. Present that reference's numbered questionnaire in your reply.
3. In the **same turn**, apply symptom-derived starter values from that reference's
   recommendation logic to the deployed copy at
   `<deploy_dir>/controller/tracker-config.json` or
   `<deploy_dir>/controller/reid-config.json` (never the skill's `assets/` originals). Show the
   exact JSON field changes and the exact restart command
   `docker compose up -d --force-recreate scene`.
4. Note that questionnaire answers can further refine the starter values.

Do not skip the questionnaire, and do not skip showing the deployed-path edits + scene-only
restart. Load exactly one matching reference (tracker timing vs cross-camera Re-ID).

## Quality & Evaluation

Automated eval cases live in [evals/evals.json](./evals/evals.json), one entry per
`example-prompts/` file (`prompt_file` links the two together). See
[benchmark/benchmark.md](./benchmark/benchmark.md) for the current benchmark.
