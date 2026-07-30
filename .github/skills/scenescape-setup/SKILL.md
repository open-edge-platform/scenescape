---
name: scenescape-setup
description: >
  Deploy a working Intel® SceneScape installation from scratch (outside the repo). Gathers
  user-provided streams, camera IDs, and scene name, then runs bootstrap through tracking
  verification via scripts/deploy_scenescape.sh. Also handles re-running or resuming a single
  phase of an existing deployment on request (e.g. "recalibrate", "redo scene reconstruction",
  "resume bootstrap only") via the orchestrator's --phase flag.
argument-hint: "<deploy_dir> — always gather streams, camera_ids, scene_name from the user first"
license: Apache-2.0
compatibility: >-
  Requires Docker, docker-compose, and Python 3.10+ with `requests` on the host. GitHub access
  for sparse checkout of dlstreamer-pipeline-server. Network access to RTSP camera streams.
---

# SceneScape End-to-End Setup

Host needs **Docker**, **docker-compose**, and **Python 3.10+** with `requests`.

## File Resolution

All scripts, references, and assets are resolved **relative to `$SKILL_DIR`**
(`$SKILL_DIR/scripts/...`, `$SKILL_DIR/references/...`, `$SKILL_DIR/assets/...`), so the skill
folder is self-contained and portable — copying just `.github/skills/scenescape-setup/` (e.g. via
an `npx skills add` style install) works the same as running from a full repo checkout. The only
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

- **Execute, don't just narrate.** Once `deploy_dir`, `streams`/video source, `camera_ids`, and
  `scene_name` are known (from the user's message, `deploy-inputs.json`, or `.deploy-state.json`),
  actually run every step yourself with your tools — download files, invoke `deploy_inputs.py`,
  launch the orchestrator, edit config files, run restart commands — instead of printing a list of
  shell snippets for the user to copy/paste. A response consisting only of a "here's what you'd
  run" plan, with no corresponding tool calls, does not satisfy this skill's task even if every
  command shown is correct. The one exception is genuinely destructive actions (see below), which
  must be shown and confirmed before executing, not skipped. This does **not** license silently
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

| Symptom                                                                  | Reference                                           |
| ------------------------------------------------------------------------ | --------------------------------------------------- |
| Tracks flicker, vanish during occlusion, or IDs change unexpectedly      | [tuning-tracker.md](./references/tuning-tracker.md) |
| Re-identification across cameras is missing or matching the wrong person | [tuning-reid.md](./references/tuning-reid.md)       |

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

## Directory Layout

Generated files under `<deploy_dir>` after a full run:

```
<deploy_dir>
├── deploy-inputs.json              # Step 1 — user inputs (source of truth, reused on resume)
├── .deploy-state.json              # Checkpoint — last completed step, scene_uid, frames_dir
├── deploy.log                      # Combined stdout/stderr for every step
├── docker-compose.yml              # Generated from docker-compose-template.md
├── secrets/                        # generate_secrets.sh, openssl.cnf (from skill assets/), certs/, django/, *.auth
├── dlstreamer-pipeline-server/     # Sparse-checked-out from upstream repo
│   ├── pipeline-config.json        # Generated per-camera pipeline (adapt_pipeline_config.py)
│   ├── model-proc-files/
│   ├── mosquitto/
│   └── user_scripts/
│       └── gstplugins/             # Native GST elements (timestamp + datapublish); compose-mounted
│                                   # into /opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0/python/
└── calibration-frames/             # Step 9 — one JPEG per user camera ID
```

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

### Execution overview

The orchestrator itself runs steps 6–13 sequentially and can take several minutes (Docker image
pulls, model downloads, RTSP warmup, scene reconstruction). Launch it in an **async terminal** and
poll for output/completion instead of blocking on it — show the actual backgrounded invocation
(e.g. your async-terminal tool, or `nohup ... & disown` if shelling out directly), not a plain
foreground command. Within step 7, the script already parallelizes internally —
`parallel_warmup.sh` and `download_detection_models.sh` run in the background while
`verify_rtsp.sh` runs in the foreground — no extra action needed there.

Your response must call out, explicitly, each of: the async launch mechanism used, that step 9
produces one calibration JPEG per `camera_id` under `calibration-frames/`, that step 13's tracking
verification confirms tracked objects are associated with more than one `camera_id` (for
multi-camera deployments), and the `DEPLOY COMPLETE` / Post-Task metrics reporting requirement
below — do not omit any of these even when summarizing for brevity.

Dependency order across phases (each phase blocks the next):

```
Step 1 (gather + persist inputs)
  └─► bootstrap (6–8: configs, RTSP/pipeline validation, full stack)
        └─► calibrate (9–10: calibration frames, mapping health)
              └─► scene (11–13: reconstruction, finalize, tracking verification)
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

## Reference Lookup

Each reference document has one primary step where it should be read; load others only when
troubleshooting a failure at that step.

| Reference                                                             | Primary step             | Purpose                                                                                                       |
| --------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------- |
| [pipeline-config.md](./references/pipeline-config.md)                 | 6                        | How `adapt_pipeline_config.py` generates per-camera pipelines (native `sscape_*` GST elements) |
| [mosquitto-config.md](./references/mosquitto-config.md)               | 6                        | Broker TLS listener layout; optional password file generation                                                 |
| [docker-compose-template.md](./references/docker-compose-template.md) | 6 (failure only)         | Full compose template; read only to debug a template bug                                                      |
| [command-templates.md](./references/command-templates.md)             | 7                        | Reusable RTSP gate check and MQTT pub/sub verification commands                                               |
| [runtime-verification.md](./references/runtime-verification.md)       | 7, 9                     | RTSP/service-health failure diagnosis                                                                         |
| [scene-and-cameras.md](./references/scene-and-cameras.md)             | 11–12 (failure only)     | Manual scene/camera REST calls if reconstruction needs inspection                                             |
| [reconstruction.md](./references/reconstruction.md)                   | 11–12                    | Reconstruction and finalization failure diagnosis; supplementing with a walk-through video                    |
| [scene-map-alternatives.md](./references/scene-map-alternatives.md)   | after Step 1 (if chosen) | Blueprint/GLB/geospatial scene creation, pixels-per-meter, manual-calibration handoff                         |
| [verify-tracking.md](./references/verify-tracking.md)                 | 13                       | Tracking verification failure diagnosis                                                                       |
| [phase-bootstrap.md](./references/phase-bootstrap.md)                 | 6–8 (standalone)         | Run/resume only the bootstrap phase                                                                           |
| [phase-calibrate.md](./references/phase-calibrate.md)                 | 9–10 (standalone)        | Run/resume only the calibrate phase                                                                           |
| [phase-scene.md](./references/phase-scene.md)                         | 11–13 (standalone)       | Run/resume only the scene phase                                                                               |
| [tuning-tracker.md](./references/tuning-tracker.md)                   | reactive (post-deploy)   | Diagnose reported tracking-quality issues → `tracker-config.json` motion/timing values                        |
| [tuning-reid.md](./references/tuning-reid.md)                         | reactive (post-deploy)   | Diagnose reported Re-ID issues → `reid-config.json` re-identification values                                  |
| [attribute-persistence.md](./references/attribute-persistence.md)     | reactive (post-deploy)   | Keep object attributes from resetting between detections via `persist_attributes`                             |
| [singleton-sensors.md](./references/singleton-sensors.md)             | reactive (post-deploy)   | Add non-perceptual/scalar sensors (environmental or attribute-type) — REST for scene-wide, UI for circle/poly |
| [object-library.md](./references/object-library.md)                   | reactive (post-deploy)   | Define expected object-class size/shape (Object Library / `Asset3D`) via REST                                 |
| [using-scene-output.md](./references/using-scene-output.md)           | reactive (post-deploy)   | Consume the regulated scene topic; wire up regions/tripwires for event-driven alerting                        |

## Assets

`assets/` holds files copied verbatim into `<deploy_dir>` by `bootstrap_deploy.py` (step 2) — the
agent never runs these directly; the generated deployment does.

| Asset                                               | Copied to                  | Purpose                                                                                                                                                |
| --------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [generate_secrets.sh](./assets/generate_secrets.sh) | `<deploy_dir>/secrets/`    | Generates TLS certs and service auth JSON files                                                                                                        |
| [openssl.cnf](./assets/openssl.cnf)                 | `<deploy_dir>/secrets/`    | Certificate extension template used by `generate_secrets.sh`                                                                                           |
| [tracker-config.json](./assets/tracker-config.json) | `<deploy_dir>/controller/` | Scene Controller tracker behavior config — tunable if the user reports tracking issues, see [tuning-tracker.md](./references/tuning-tracker.md)        |
| [reid-config.json](./assets/reid-config.json)       | `<deploy_dir>/controller/` | Re-identification model config for multi-camera tracking — tunable if the user reports Re-ID issues, see [tuning-reid.md](./references/tuning-reid.md) |

## Examples

See [example-prompts](./example-prompts) for ready-to-use prompts covering a multi-camera
deployment, resuming after a camera/stream change, and reactive tracker/Re-ID tuning after a
deployment is already running. For deploying from an existing blueprint/GLB mesh or a geospatial
map instead of auto-reconstruction, see
[scene-map-alternatives.md](./references/scene-map-alternatives.md). For attribute persistence,
singleton sensors, or Object Library entries after a deployment is running, see
[attribute-persistence.md](./references/attribute-persistence.md),
[singleton-sensors.md](./references/singleton-sensors.md), and
[object-library.md](./references/object-library.md). For consuming the scene's output or wiring
up regions/tripwires, see [using-scene-output.md](./references/using-scene-output.md).

## Quality & Evaluation

Automated eval cases live in [evals/evals.json](./evals/evals.json), one entry per
`example-prompts/` file (`prompt_file` links the two together). See [BENCHMARK.md](./BENCHMARK.md)
for current benchmark status.

## Writing an effective prompt

A good initial request answers these up front so Step 1 can be skipped or confirmed in one pass:

| Field        | Example                                        |
| ------------ | ---------------------------------------------- |
| `deploy_dir` | `~/deployments/warehouse-demo`                 |
| `streams`    | `rtsp://192.168.1.10:8554/cam1`                |
| `camera_ids` | `cam1` (unique, no `/`, same order as streams) |
| `scene_name` | `Warehouse Floor 1`                            |

If any field is missing, the agent asks for it (Step 1) before running the orchestrator.

## Post-Task — Report deployment metrics

After `DEPLOY COMPLETE`, report a short breakdown in the same response as the completion message:

1. **Requirements gathering time** — Step 1 Q&A and validation
2. **Bootstrap time** — steps 6–8 (configs, RTSP/pipeline warmup, full stack)
3. **Calibration time** — steps 9–10 (calibration frames, mapping health)
4. **Scene + verification time** — steps 11–13 (reconstruction, finalize, tracking)
5. **Total wall-clock time** (phases may overlap with user wait time, so total ≠ strict sum)

## Post-Task — Web UI access

In the same response as `DEPLOY COMPLETE`, always tell the user how to view the scene and live
tracks in the browser:

- **URL**: `https://localhost` (port 443 on the Docker host — the `web` service publishes
  `443:443`). Use `localhost` unless the user is browsing from a different machine, in which case
  substitute the deploy host's IP/hostname. The browser will warn on the self-signed cert; accept/
  proceed to continue.
- **Do not** suggest `https://web.scenescape.intel.com` — that hostname is only a Docker network
  alias resolvable _inside_ the compose network (containers, `curl`/`mosquitto` from within
  scripts); it has no DNS entry on the host and will fail to resolve in a browser unless the user
  has manually added it to their `/etc/hosts`.
- **Username**: `admin`
- **Password**: read from `<deploy_dir>/secrets/supass` (e.g. `cat <deploy_dir>/secrets/supass`) —
  never print the password value itself in chat; point the user to the file (or the `supass=`
  value already echoed by the orchestrator's `DEPLOY COMPLETE` line if the user is looking at that
  terminal output themselves).
- After login, the scene created by this deployment (`scene_name` from Step 1) appears on the
  scenes list; open it to see the live camera feeds and tracked-object overlay on the generated
  map/mesh.

## After deployment — guide the user toward a goal

A deployment alone rarely is the end goal — ask what the user wants to do with the tracked-object
data (alert, count, dashboard, integration) in the same response as the metrics report, then load
only the matching option from [using-scene-output.md](./references/using-scene-output.md). Treat
the answer as a seed for the user's broader intent across later requests in the session.

## Prerequisites

- GitHub access (sparse checkout of `dlstreamer-pipeline-server`)
- Proxy: `http_proxy` / `https_proxy` / `no_proxy`; RTSP Docker hostnames appended automatically
- TLS certs generated in step 6; superuser password in `secrets/supass`
