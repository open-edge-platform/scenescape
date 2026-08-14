<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Agent guardrails and safety rules

Read once before launching any deploy/resume/phase. Non-negotiable constraints for autonomous
execution.

## Safety rules for autonomous execution

- **Execute approved deployment work, don't just narrate.** After the user explicitly requests a
  deployment and `deploy_dir`, `streams`/video source, `camera_ids`, `scene_name`, and `mapping`
  are known (from the user's message, `deploy-inputs.json`, or `.deploy-state.json`), use tools to
  perform the approved non-destructive steps instead of providing shell snippets alone. Show and
  obtain confirmation for genuinely destructive actions (see below) before executing them. This
  does **not** license silently merging a changed `camera_id`/stream into the existing
  `deploy-inputs.json` on the user's behalf — a camera/stream change still requires showing the
  user the full updated `streams`/`camera_ids`/`scene_name` set (existing entries you read back
  plus the new one) and getting their confirmation before writing it or running `--fresh`, per
  the Fast Path rule. If your environment/tooling explicitly forbids real network calls or
  starting real services (e.g. a constrained eval or sandboxed run), say so plainly and still
  produce the exact commands you would have run and their expected results — do not silently
  skip steps without saying why.
- Before running any command that installs packages, generates secrets, pulls Docker images, or
  brings up containers for the first time, show the exact command and proceed only after the
  user's initial request already approved this deployment (asking again for every routine step
  is not required, but destructive actions — `--fresh`, deleting `deploy_dir` contents,
  `docker compose down -v` — always require explicit confirmation).
- **Never** interpolate raw `streams`, `camera_ids`, or `scene_name` values directly into ad hoc
  shell one-liners. Always pass them as quoted arguments to `deploy_inputs.py` / the orchestrator
  (the existing scripts already do this) so validation and JSON-escaping happen in one place.
- Restrict file writes to `<deploy_dir>` and `$SKILL_DIR`; do not write outside those paths
  unless the user explicitly approves a wider scope.

## Agent guardrails

- **Step 1 is mandatory on a new deploy** — ask the user for `streams`, `camera_ids`,
  `scene_name`, and `mapping`. Do not assume values from prior sessions, sample data, or
  running containers.
- **Prefer the orchestrator** after inputs are confirmed; read `deploy.log` only on failure.
- Before executing an orchestrator command, obtain the user's authorization to deploy or resume;
  an explicit request to deploy, continue, or resume is sufficient. Otherwise, show the command
  and ask. Always obtain separate explicit confirmation before executing `--fresh`.
- **Do not read** `assets/docker-compose-template.md` or `sample_data/` unless troubleshooting a
  template bug. Pipeline generation is defined in `pipeline-config.md`.
- **Do not** dump raw `docker compose logs`; use `check_service_health.py` and focused log
  filters.
- **Resume** with `--deploy-dir` only when `deploy-inputs.json` exists **or when the user's
  message contains a clear resume signal** ("continue", "resume", "stopped partway through",
  "pick up where we left off", etc.) — in that case, treat the signal as confirmation the file
  exists without checking the filesystem. Follow the authorization guardrail above before launch.
  Only fall back to Step 1 if the user says the directory is wrong or no prior run was started.
  Use `--fresh` when cameras or streams change.
- For a resume response, run `deploy_inputs.py read` before the launch and explicitly label the
  loaded `streams`, `camera_ids`, and `scene_name` as the values the user is confirming. Use the
  exact resume invocation in the Fast Path; do **not** add `--resume`, because resume is already
  the orchestrator default and the command must contain only `--deploy-dir` and `--skill-dir`.
- Load troubleshooting references only when a step fails.
- **Never** assign `SKILL_DIR` inline with `bash` on the same command (`SKILL_DIR=x bash
  "$SKILL_DIR/..."` silently fails because the variable is not yet expanded). Always set
  `export SKILL_DIR=...` on its own line first.
- **Always attach the completion watcher** when launching the orchestrator (full deploy, resume,
  or `--phase`). Do **not** ask the user to poll for status; report back when the watcher
  notifies `RESULT=`.
