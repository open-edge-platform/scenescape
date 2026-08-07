---
name: scenescape-setup
description: >
  Deploy a working Intel® SceneScape installation from scratch (outside the repo). Gathers
  user-provided streams, camera IDs, and scene name, then runs bootstrap through tracking
  verification via scripts/deploy_scenescape.sh. Also handles re-running or resuming a single
  phase of an existing deployment on request (e.g. "recalibrate", "redo scene reconstruction",
  "resume bootstrap only") via the orchestrator's --phase flag.
license: Apache-2.0
compatibility: >-
  Requires Docker, docker-compose, and Python 3.10+ with `requests` on the host. GitHub access
  for sparse checkout of dlstreamer-pipeline-server. Network access to RTSP camera streams.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, Env
metadata:
  argument-hint: "<deploy_dir> — always gather streams, camera_ids, scene_name from the user first"
---

# SceneScape End-to-End Setup

Host needs **Docker**, **docker-compose**, and **Python 3.10+** with `requests`.

## File Resolution

All scripts, references, and assets are resolved **relative to `$SKILL_DIR`**
(`$SKILL_DIR/scripts/...`, `$SKILL_DIR/references/...`, `$SKILL_DIR/assets/...`), so the skill
folder is self-contained and portable — copying just `.github/skills/scenescape-setup/` with a
standalone skill installer works the same as running from a full repo checkout. The only
exception is Step 0's "Extract from git" fallback, which assumes a local SceneScape clone exists
somewhere on disk; skip it and go straight to Step 0.A whenever `$SKILL_DIR/scripts/deploy_scenescape.sh`
already exists (true for any pre-installed copy of this skill).

References that point at `docs/user-guide/...` in the SceneScape repo (e.g.
`data_formats.md`, `how-to-configure-tracker.md`, `Extended-ReID.md`) assume that path exists
relative to a local checkout. **Never copy that documentation's content into a `references/`
file** — it would create a second copy that silently drifts out of sync as SceneScape evolves.
When a local checkout isn't available (this skill folder was copied standalone) and the doc path
doesn't resolve, fall back to the canonical GitHub URL instead of guessing at the content:
`https://github.com/open-edge-platform/scenescape/blob/main/<path>`. Prefer the local path first
(works fully offline); only reach for the GitHub URL as a secondary fallback, and if neither is
reachable, say so rather than fabricating field names/values from memory. Reserve new
`references/` files for knowledge that has no existing written form anywhere else — e.g. the
tuning questionnaires' symptom-to-config-value mappings, which aren't documented as a procedure
in `docs/user-guide/`.

## Safety rules for autonomous execution

- **Execute approved deployment work, don't just narrate.** After the user explicitly requests a
  deployment and `deploy_dir`, `streams`/video source, `camera_ids`, and `scene_name` are known
  (from the user's message, `deploy-inputs.json`, or `.deploy-state.json`), use tools to perform
  the approved non-destructive steps instead of providing shell snippets alone. Show and obtain
  confirmation for genuinely destructive actions (see below) before executing them. This does
  **not** license silently
  merging a changed `camera_id`/stream into the existing `deploy-inputs.json` on the user's
  behalf — a camera/stream change still requires showing the user the full updated
  `streams`/`camera_ids`/`scene_name` set (existing entries you read back plus the new one) and
  getting their confirmation before writing it or running `--fresh`, per the Fast Path rule below.
  If your environment/tooling explicitly forbids real network calls or starting real services
  (e.g. a constrained eval or sandboxed run), say so plainly and still produce the exact commands
  you would have run and their expected results — do not silently skip steps without saying why.
- Before running any command that installs packages, generates secrets, pulls Docker images, or
  brings up containers for the first time, show the exact command and proceed only after the
  user's initial request already approved this deployment (asking again for every routine step is
  not required, but destructive actions — `--fresh`, deleting `deploy_dir` contents, `docker compose
down -v` — always require explicit confirmation).
- **Never** interpolate raw `streams`, `camera_ids`, or `scene_name` values directly into ad hoc
  shell one-liners. Always pass them as quoted arguments to `deploy_inputs.py` / the orchestrator
  (the existing scripts already do this) so validation and JSON-escaping happen in one place.
- Restrict file writes to `<deploy_dir>` and `$SKILL_DIR`; do not write outside those paths unless
  the user explicitly approves a wider scope.

## Agent guardrails

- **Step 1 is mandatory on a new deploy** — ask the user for `streams`, `camera_ids`, and
  `scene_name`. Do not assume values from prior sessions, sample data, or running containers.
- **Prefer the orchestrator** after inputs are confirmed; read `deploy.log` only on failure.
- **Do not read** `docker-compose-template.md` or `sample_data/` unless troubleshooting a
  template bug. Pipeline generation is defined in `pipeline-config.md`.
- **Do not** dump raw `docker compose logs`; use `check_service_health.py` and focused log filters.
- **Resume** with `--deploy-dir` only when `deploy-inputs.json` exists **or when the user's
  message contains a clear resume signal** ("continue", "resume", "stopped partway through",
  "pick up where we left off", etc.) — in that case, treat the signal as confirmation the file
  exists and apply the Fast Path directly without checking the filesystem. Only fall back to
  Step 1 if the user says the directory is wrong or no prior run was started. Use `--fresh`
  when cameras or streams change.
- For a resume response, run `deploy_inputs.py read` before the launch and explicitly label the
  loaded `streams`, `camera_ids`, and `scene_name` as the values the user is confirming. Use the
  exact resume invocation in the Fast Path; do **not** add `--resume`, because resume is already
  the orchestrator default and the command must contain only `--deploy-dir` and `--skill-dir`.
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
git -C "$SCENESCAPE_REPO" fetch origin main
mkdir -p /tmp/scenescape-skill
git -C "$SCENESCAPE_REPO" archive origin/main \
  -- .github/skills/scenescape-setup | tar -x -C /tmp/scenescape-skill
export SKILL_DIR=/tmp/scenescape-skill/.github/skills/scenescape-setup
```

Verify: `ls "$SKILL_DIR/scripts/deploy_scenescape.sh"` must succeed before continuing.

## Step 1 — Gather inputs (required)

Ask the user for every new deployment:

| Input        | Rules                                                                                                |
| ------------ | ---------------------------------------------------------------------------------------------------- |
| `deploy_dir` | Writable directory for generated files                                                               |
| `streams`    | One RTSP/RTSPS URL per camera, user-provided, in order — **or** local video files/folder (see below) |
| `camera_ids` | Unique IDs (no `/`), same order as `streams`                                                         |
| `scene_name` | Human-readable scene name chosen by the user                                                         |

Validate: `len(streams) == len(camera_ids)`, ≥1 camera, `camera_ids` are unique (no duplicates, no `/`), valid RTSP URLs. State explicitly in your response that this uniqueness check was performed before writing `deploy-inputs.json` — `deploy_inputs.py` also re-validates it, but call it out for the user.

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

**No live RTSP cameras available?** If the user instead has a folder of recorded video files, or
an explicit list of video file paths, use `--video-dir`/`--video-files` in place of `--streams` —
see [video-file-input.md](./references/video-file-input.md). This covers local file playback
only; MJPEG and USB camera input are out of scope pending a separate source-discovery service.

## Scene source: reconstruction vs. blueprint/GLB vs. geospatial map

Also during Step 1, ask:

> "Do you already have a floor blueprint image or a `.glb`/`.ply` scene mesh, or should
> SceneScape auto-generate the scene map from camera reconstruction (default)? If you'd rather
> build the scene from a geospatial (address/GPS-based) map, that's also available."

- **No answer / reconstruction (default)**: proceed as documented below — the orchestrator's
  steps 9 and 11–13 capture calibration frames, auto-generate the map, and auto-calibrate camera
  poses. If the user also has a pre-recorded walk-through video of the space, it can be included
  at step 11–12 for extra reconstruction coverage (camera auto-calibration is unaffected) — see
  [reconstruction.md](./references/reconstruction.md#supplementing-with-a-walk-through-video).
- **Blueprint image, GLB/PLY mesh, or geospatial map**: this skips automatic camera-pose
  estimation, so the user must calibrate cameras **manually** via the web UI afterward — confirm
  they accept that tradeoff, then follow
  [scene-map-alternatives.md](./references/scene-map-alternatives.md), which covers running only
  `--phase bootstrap`/`--phase calibrate`, computing pixels-per-meter for a blueprint, creating the
  scene via REST, and (for geospatial) setting `output_lla` + `map_corners_lla`.

## Tuning tracker/Re-ID behavior (reactive only)

Do **not** ask tuning questions upfront during Step 1 — always deploy with the shipped
`tracker-config.json` / `reid-config.json` defaults first. Only open the relevant questionnaire
below **after** a deployment is running and the user reports dissatisfaction with tracking
quality (e.g. "objects flicker/disappear", "IDs keep changing", "it's not re-identifying people
across cameras", "tracking feels wrong for my scene").

When that happens, present only the questionnaire matching the reported symptom — write out its
numbered questions in your response — rather than the full combined set from both tuning
references. If you're in a non-interactive session and cannot wait for a reply, still show every
question from that questionnaire explicitly alongside your best-inferred answer (state the
inference plainly, e.g. "assuming X based on <evidence from the report>"), so the user can see
and correct any assumption, instead of silently skipping straight to a recommendation with no
questions shown. Then **actually apply** the resulting values yourself — edit
`<deploy_dir>/controller/tracker-config.json` and/or `reid-config.json` with your file-editing
tool (not a suggested diff for the user to paste) and run `docker compose up -d --force-recreate
scene` yourself (not a suggested command) to pick up the change:

For tracker tuning, the first response must render these five numbered questions before proposing
any configuration values: highest camera FPS; camera field-of-view overlap; whether objects are
mostly moving or static; expected occlusion duration/frequency; and whether UI stability matters
more than brief flicker. In a non-interactive environment, include each question with its stated
assumed answer; do not replace the questionnaire with a prose assumption.

| Symptom                                                                  | Reference                                           |
| ------------------------------------------------------------------------ | --------------------------------------------------- |
| Tracks flicker, vanish during occlusion, or IDs change unexpectedly      | [tuning-tracker.md](./references/tuning-tracker.md) |
| Re-identification across cameras is missing or matching the wrong person | [tuning-reid.md](./references/tuning-reid.md)       |

Before diagnosing a reactive tuning request, use the file-reading tool to load exactly one
matching reference: load `references/tuning-tracker.md` for occlusion, flicker, disappearing
tracks, or unexpected IDs in the same camera path; load `references/tuning-reid.md` for
identity failures between cameras. Do not load the other tuning reference. State which reference
you used in the response so the user can see whether the problem was treated as tracker timing
or cross-camera Re-ID.

Name the edited target as the deployed `<deploy_dir>/controller/tracker-config.json` or
`<deploy_dir>/controller/reid-config.json` copy and explicitly distinguish it from the matching
`assets/` file in the skill, which must remain unchanged.

## Other optional scene configuration (reactive only)

These are additional manager capabilities beyond the core deploy flow. Like tuning, do not ask
about them upfront in Step 1 — load the matching reference only when the user's request implies
one of these needs:

| User need                                                                                        | Reference                                                         |
| ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| Keep a **vision/AI-pipeline** attribute (color, license plate, person attributes) from resetting | [attribute-persistence.md](./references/attribute-persistence.md) |
| Feed the scene an **external, non-vision** reading or event (temperature, badge swipe, etc.)     | [singleton-sensors.md](./references/singleton-sensors.md)         |
| Define expected size/shape for a detected object class (Object Library)                          | [object-library.md](./references/object-library.md)               |

If the user says "attribute" without more context, ask whether the value comes from the camera/AI
pipeline (→ attribute-persistence.md) or from a separate sensor publishing its own MQTT messages
(→ singleton-sensors.md) — both docs cross-reference each other for this exact ambiguity.

## Fast Path (repeat or resume deployments)

If `<deploy_dir>/deploy-inputs.json` already exists and the user's new request does not change
streams, camera IDs, or the scene name, skip re-asking Step 1 questions:

1. Show the loaded `deploy-inputs.json` values to the user and confirm they still apply.
2. Run the orchestrator with `--deploy-dir` + `--skill-dir` only (no `--streams`/`--camera-ids`/
   `--scene-name`) — inputs are loaded automatically and validated against any values the user did
   provide.
3. If the user mentions a camera/stream change, treat it as a new deployment: re-run Step 1 in
   full and use `--fresh`.

For a restricted environment where the read-back cannot expose the file's contents, still show a
three-field confirmation block for the persisted `streams`, `camera_ids`, and `scene_name`; say
they are loaded from `deploy-inputs.json` rather than inventing replacement inputs. A resume
command must omit `--resume`, `--streams`, `--camera-ids`, and `--scene-name`.

**Implicit Fast Path trigger**: When the user says "continue", "resume", "it stopped partway
through", "pick up where we left off", or similar for a named `deploy_dir`, treat that statement
as confirmation that `deploy-inputs.json` already exists at that path. Apply the Fast Path
directly — show the user the Fast Path procedure (what values will be loaded and what command will
be run) without falling back to Step 1 questions. Only fall back to Step 1 if:

- The user explicitly says the directory is wrong or no prior run exists.
- You attempt to read `deploy-inputs.json` and the file is genuinely absent **and** the user did
  not give any "resume/continue" signal — a new fresh deployment was intended.

For an explicit resume signal, do not test the local sandbox for file existence or treat a missing
local path as a contradiction. The signal is sufficient confirmation: show the read-back command,
show the resume command, and state that `.deploy-state.json` selects the next incomplete step.

For a camera or stream change, read the existing inputs before creating the replacement set. If
the read-back is unavailable, say that the new set replaces only the named camera/stream while
retaining every other persisted camera, stream, and the scene name, then explicitly ask the user
to confirm or provide that existing list. Do not proceed with only the changed camera.

In that unavailable-read-back case, do not execute a write or `--fresh` launch. State: "I could
not read the existing deployment inputs. Please provide or confirm the retained camera IDs,
streams, and scene name before the fresh redeploy." Then show the exact `--fresh` orchestrator
command marked **pending confirmation**, explaining that it clears `.deploy-state.json` and the
old `deploy-inputs.json`, and reruns **bootstrap**, **calibrate**, and **scene** rather than only
recalibrating the changed camera. Never present retained-camera placeholders as runnable values.
Use this exact sentence in the response: "`--fresh` clears `.deploy-state.json` and the old
`deploy-inputs.json`."

## Deploy and complete

After Step 1, read [operational-reference.md](./references/operational-reference.md) for the
orchestrator command, generated-file layout, phase sequence, troubleshooting references, and
completion handoff. Launch the orchestrator asynchronously. Every full-deployment response must
state that step 9 produces one calibration JPEG per camera ID; step 13 confirms tracked objects
are associated with more than one `camera_id`; and success is `DEPLOY COMPLETE` with a `scene_uid`.
It must also enumerate requirements-gathering, bootstrap, calibration, scene-and-verification,
and total wall-clock metrics. The launch command itself must be backgrounded (for example,
`nohup ... >"$DEPLOY_DIR/orchestrator.log" 2>&1 &`), not merely described as asynchronous.

## Running a single phase

If the user asks to (re)run, resume, or redo just one phase of an already-started deployment
(rather than a full end-to-end deploy), use the orchestrator's `--phase` flag directly instead of
omitting it (see flags table above). Load the matching reference **only** for that request — it
has the phase's prerequisites, narrower safety rules, and standalone `Run` command:

| Phase     | Steps | Reference                                             |
| --------- | ----- | ----------------------------------------------------- |
| bootstrap | 6–8   | [phase-bootstrap.md](./references/phase-bootstrap.md) |
| calibrate | 9–10  | [phase-calibrate.md](./references/phase-calibrate.md) |
| scene     | 11–13 | [phase-scene.md](./references/phase-scene.md)         |

A single-phase request still requires `deploy-inputs.json` to already exist for that
`deploy_dir` (from a prior Step 1) — do not re-ask Step 1 questions unless the user is also
changing streams/camera_ids/scene_name.

## Quality & Evaluation

Automated eval cases live in [evals/evals.json](./evals/evals.json), one entry per
`example-prompts/` file (`prompt_file` links the two together). See
[evals/benchmark.md](./evals/benchmark.md) for the current benchmark.
