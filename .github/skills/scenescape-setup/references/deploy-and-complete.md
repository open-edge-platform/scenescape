<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Deploy and complete

Read after Step 1 inputs are confirmed (or Fast Path loaded) for any orchestrator launch — full
deploy, resume, or `--phase`.

Launch the default all-phase deployment asynchronously, then **immediately** start the
completion watcher. Capture the orchestrator PID (`$!`) and pass it to `watch_orchestrator.sh`
so the agent is notified when the run finishes — do not ask the user to poll with "status".

```bash
nohup bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --streams <rtsp_url> [...] \
  --camera-ids <id> [...] \
  --scene-name <scene_name> \
  >"<deploy_dir>/orchestrator.log" 2>&1 &
ORCH_PID=$!
echo "$ORCH_PID" >"<deploy_dir>/orchestrator.pid"

# Background this watcher (do not block the agent turn). Configure tool notify_on_output
# (or equivalent) with pattern: RESULT=
bash "$SKILL_DIR/scripts/watch_orchestrator.sh" \
  --deploy-dir <deploy_dir> \
  --pid "$ORCH_PID"
```

## Watcher rules (mandatory on every orchestrator launch, including Fast Path resume and `--phase`)

1. Start `watch_orchestrator.sh` in the background right after the orchestrator
   (`block_until_ms: 0` or equivalent). Pass the real orchestrator PID — never `pgrep` for
   `deploy_scenescape.sh` (that can match the watcher or the launching shell).
2. Subscribe to output matching `RESULT=` so the agent is woken when the run ends.
3. Tell the user the deploy/resume is running and that you will report when it completes; do
   **not** instruct them to keep asking for status.
4. When notified: on `RESULT=SUCCESS`, report `DEPLOY COMPLETE` / `scene_uid`, write the
   deployment README (below), include Post-task metrics, then run the post-deploy handoff
   below. On `RESULT=FAILURE`, read only the matching troubleshooting reference for the failed
   step and continue diagnosis — do not dump full compose logs.

For a video-file deployment, use the synthesized RTSP streams from `deploy_inputs.py read` in
the same command. Every full-deployment response (including dry-run / plan-only harness runs)
must state all of the following in the response text itself — not only as comments inside a
shell snippet:

- Step 9 produces one calibration JPEG per camera ID.
- Step 13 confirms tracked objects are associated with more than one `camera_id`.
- Success is marked by `DEPLOY COMPLETE` with a `scene_uid`.
- The watcher is subscribed with notify pattern `RESULT=` (use that exact token).
- A `Post-task metrics` breakdown listing these five categories:
  requirements-gathering, bootstrap, calibration, scene-and-verification, and total
  wall-clock.

Use this exact sentence when describing the watcher: "Notify on `RESULT=` so completion is
reported without asking the user to poll status." Use this exact sentence for the metrics
header: "Post-task metrics: requirements-gathering, bootstrap, calibration,
scene-and-verification, total wall-clock."

## Deployment README (after `DEPLOY COMPLETE`)

Read [readme-template.md](./readme-template.md), substitute the tokens (`{{SCENE_NAME}}`,
`{{DEPLOY_DIR}}`, `{{SCENE_UID}}`, `{{CAMERA_IDS}}`, and `{{HOST_IP}}` from
`ip -4 route get 8.8.8.8 | awk '{print $7; exit}'`), and write the result to
`<deploy_dir>/README.md`. Skip silently if the template is missing.

## Post-deploy handoff (required after every successful full deploy)

Read [using-scene-output.md](./using-scene-output.md) and end the success response with its
clarifying question (what the user wants to do with the tracked-object data — alert, count,
integrate, or something else). Do this even if the user has not asked yet; do **not** skip it
after metrics/README. Single-phase `--phase` successes skip this handoff unless the user is
continuing into application/analytics work.

Do **not** read [operational-reference.md](./operational-reference.md) during a routine deploy
or resume. Read it only for a requested generated-file-layout or web-UI handoff, or when a
specific bootstrap, runtime, reconstruction, or tracking-verification failure needs diagnosis.
