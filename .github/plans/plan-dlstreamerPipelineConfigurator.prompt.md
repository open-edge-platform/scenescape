<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

## Plan: Integrate DLS Pipeline Configurator

Add an optional pipeline-customization path to scenescape-setup that invokes the external dlstreamer-coding-agent only when the user supplies a customization prompt, consumes a single generated GStreamer pipeline string, normalizes it into SceneScape-compatible `pipeline-config.json` entries (timestamp capture, metaconvert, data-publish element names, policy constraints), and then continues the existing deployment gates. Basic deployments keep today's `adapt_pipeline_config.py` defaults with no external dependency; fail fast only when customization was requested and cannot be satisfied.

This revision reflects the current skill: the `gvapython` + `sscape_adapter.py` path is gone and replaced by native GStreamer Python plugins under `dlstreamer-pipeline-server/user_scripts/gstplugins/`, phases live as `references/phase-*.md` inside one skill rather than separate skill folders, and orchestrator step numbers are already in use from 6 through 13.

**Steps**

1. Phase 1 — Discovery hardening and interface contract
   - Define the external invocation contract in a new `references/pipeline-customization.md`: input payload (camera_ids, streams, user prompt, optional model/device hints), expected output (a single GStreamer pipeline string), and error shape.
   - Add the guardrail that external invocation is conditional: run only when a new input field `pipeline_customization_prompt` is non-empty, otherwise preserve the current `adapt_pipeline_config.py` flow unchanged. _blocks all later logic_
   - Abstract the invocation mechanism behind an environment-configurable command with JSON on stdin/stdout, plus timeout and retry behavior, so setup scripts hardcode no network or repo assumptions. _depends on previous step_

2. Phase 2 — Setup input model updates
   - Extend `inputs_payload()` in `scripts/deploy_inputs.py` with optional `pipeline_customization_prompt` and `pipeline_customization_mode`, leaving the existing keys (`scene_name`, `camera_ids`, `streams`, `source_type`, optional `video_paths`, `skill_dir`) untouched.
   - Decide explicitly whether the new field participates in `inputs_match()`. It currently compares only scene_name, camera_ids, and streams, and the `check` subcommand builds its candidate payload without the new field, so changing one side without the other silently breaks resume. _depends on previous step_
   - Update Step 1 in `SKILL.md` to ask for the optional prompt and document when external invocation occurs. _parallel with next step_
   - Load prompt state from `deploy-inputs.json` on resume in `scripts/deploy_scenescape.sh` and include it in the consistency check. _depends on deploy_inputs.py changes_

3. Phase 3 — Pipeline configurator script
   - Add `scripts/configure_pipeline.py` that reads `<deploy_dir>/dlstreamer-pipeline-server/pipeline-config.json`, no-ops with an explicit log when no prompt is present, invokes the external wrapper for a single pipeline string when one is, validates and normalizes that string, and writes updated per-camera entries while keeping the `config.logging` / `config.pipelines` envelope unchanged.
   - Normalize against the native element pipeline, not gvapython: `rtspsrc add-reference-timestamp-meta=true`, `sscape_timestamp_capture name=timesync ntp-server=…`, `gvametaconvert add-tensor-data=true name=metaconvert`, `sscape_post_inference_data_publish name=datapublisher`, and the terminal `gvametapublish name=destination ! appsink sync=true`.
   - Treat element names as load-bearing: `payload.parameters` bind to elements by name (`timesync`, `datapublisher`) through the `parameters` schema, so a generated pipeline that renames or omits either element must be rejected or renamed during normalization.
   - Apply strict fail-fast behavior only in customized mode, when the generated pipeline cannot be normalized and defaults cannot satisfy the request.
   - Do not add a separate `scenescape-setup-pipeline-config` skill folder; document the step as a reference inside the existing skill, matching how phases are organized today.

4. Phase 4 — Orchestrator integration without renumbering
   - Run the configurator inside existing step 6, immediately after `adapt_pipeline_config.py` generates the config within `bootstrap_deploy.py`.
   - Rationale for dropping the original "insert step 7 and renumber" approach: steps are currently 6 bootstrap, 7 warmup/RTSP/models, 8 full stack, 9 calibration frames, 10 mapping health, 11–12 reconstruct, 13 tracking, with `phase_start_step`/`phase_end_step` mapping bootstrap to 6–8, calibrate to 9–10, and scene to 12–13. Inserting a new integer step shifts every downstream number and invalidates existing `.deploy-state.json` checkpoints, which contradicts this plan's own compatibility requirement.
   - Expose standalone re-runs as a documented direct script invocation rather than a new `--phase` value, keeping `--phase all|bootstrap|calibrate|scene` and its usage text unchanged.
   - If a dedicated phase is still wanted later, add it as a named phase mapped onto step 6 instead of a new step number.

5. Phase 5 — Policy and schema consistency safeguards
   - Validate `metadatagenpolicy` against `dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_policies.py`, which defines `detectionPolicy`, `detection3DPolicy`, `reidPolicy`, `classificationPolicy`, and `ocrPolicy`. The former source of truth, `sscape_adapter.py`, no longer exists.
   - Note that `sscape_post_inference_data_publish.py` already rejects unknown values via its `METADATA_POLICIES` check in `do_set_property`, so the script's role is to fail at configuration time rather than at container start.
   - Keep the `parameters` schema in the element/property form emitted by `adapt_pipeline_config.py` (`{"element": {"name": …, "property": …}, "type": …}`) rather than the former nested kwarg blobs.
   - Keep camera-data compatibility assumptions explicit and do not alter the MQTT payload contract in this task.

6. Phase 6 — Documentation updates
   - Update `SKILL.md`: add the optional prompt to the inputs table, note in the step map that customization runs inside step 6, and add the new reference to the reference-lookup table.
   - Update `references/pipeline-config.md` with the dual default/customized path and the normalization rules, alongside the existing plugin table.
   - Update `references/phase-bootstrap.md` to mention that bootstrap can now invoke the configurator.
   - No step-number edits are needed in `references/phase-calibrate.md` or `references/phase-scene.md`, since numbering is unchanged.
   - Keep new tables compact. `.github/skills/` is now prettier-ignored, so alignment padding is not reintroduced automatically and wide tables only cost context.
   - Add user-guide docs under `docs/user-guide/other-topics/` only if the behavior is user-visible beyond the skill docs.

7. Phase 7 — Verification plan
   - Static validation: run the repository's Python and shell lint targets for touched files, plus `make prettier-check` for any docs outside `.github/skills/`.
   - Security re-scan: run `skillspector scan .github/skills/scenescape-setup --no-llm --baseline .skillspector-baseline.yaml`. `configure_pipeline.py` will introduce new AST4 subprocess findings that must be reviewed and, if accepted, appended to the baseline.
   - Behavioral validation A (default mode): run the bootstrap flow with no prompt and verify the generated `pipeline-config.json` is unchanged from baseline behavior.
   - Behavioral validation B (custom mode success): supply a prompt requesting a reid or classification policy and verify the pipeline string and payload policy are updated while timestamp capture and metaconvert requirements survive.
   - Behavioral validation C (custom mode failure): supply an incompatible prompt and verify deployment stops with an actionable error.
   - Resume validation: checkpoint after step 6, rerun with `--resume`, and confirm no drift now that step numbering is untouched.

**Relevant files**

Paths are repo-relative to the SceneScape checkout. Note that `.cursor/skills/scenescape-setup` is a symlink to `.github/skills/scenescape-setup`, so there is a single canonical copy to edit.

- `.github/skills/scenescape-setup/SKILL.md` — optional prompt input, step-map note, reference-table entry.
- `.github/skills/scenescape-setup/references/phase-bootstrap.md` — bootstrap scope and invocation guidance.
- `.github/skills/scenescape-setup/references/pipeline-config.md` — document the default and customized paths plus policy constraints.
- `.github/skills/scenescape-setup/references/pipeline-customization.md` — new: external invocation contract, error shape, standalone re-run command.
- `.github/skills/scenescape-setup/scripts/deploy_scenescape.sh` — resume/consistency handling for the new input; no step renumbering.
- `.github/skills/scenescape-setup/scripts/deploy_inputs.py` — persist and validate the optional customization prompt.
- `.github/skills/scenescape-setup/scripts/bootstrap_deploy.py` — call the configurator after pipeline generation inside step 6.
- `.github/skills/scenescape-setup/scripts/adapt_pipeline_config.py` — keep the baseline defaults path; optionally expose reusable helpers for the configurator.
- `.github/skills/scenescape-setup/scripts/configure_pipeline.py` — new: customization and external-invocation orchestrator.
- `.github/skills/scenescape-setup/.skillspector-baseline.yaml` — update if the new script adds accepted findings.
- `dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_policies.py` — source of truth for supported metadata policies.
- `dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_post_inference_data_publish.py` — element properties and runtime policy validation.
- `dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_post_decode_timestamp_capture.py` — timestamp-capture element properties.

**Verification**

1. Run targeted script-level checks for `deploy_inputs.py`, `configure_pipeline.py`, and `adapt_pipeline_config.py`.
2. Execute the bootstrap phase without a prompt and confirm no behavioral drift in `pipeline-config.json`.
3. Execute bootstrap with a prompt and confirm per-camera pipeline entries are updated and valid.
4. Validate the fail-fast path with a prompt requesting an unsupported policy and confirm a non-zero exit with clear diagnostics.
5. Validate resume by replaying from a step 6 checkpoint with `--resume`.
6. Re-run skillspector with the committed baseline and confirm no unreviewed findings.

**Decisions**

- External invocation is conditional, not mandatory.
- The contract from the external agent is a single GStreamer pipeline string.
- Supported policies are those the native publish element accepts: `detectionPolicy`, `detection3DPolicy`, `reidPolicy`, `classificationPolicy`, and `ocrPolicy`. This supersedes the earlier three-policy v1 list, which predated the native plugins.
- Customization runs inside existing step 6 rather than as a new numbered step, to preserve `.deploy-state.json` compatibility. This supersedes the earlier "insert step 7 and renumber" decision.
- Phase documentation stays inside the single scenescape-setup skill as `references/phase-*.md`; no new sibling skill folders. This supersedes the earlier `scenescape-setup-pipeline-config` folder decision.
- If the user requested customization and defaults cannot satisfy it, stop the deployment.
- Basic deployments continue using `adapt_pipeline_config.py` defaults with no external dependency.

**Further Considerations**

1. Invocation transport: implement a thin adapter command interface first (environment-driven command with JSON stdin/stdout) to avoid coupling setup logic to one remote execution path.
2. Compatibility: keep `configure_pipeline.py` strictly additive to `pipeline-config.json` and avoid changing tracker or schema payload structure in this iteration.
3. Future enhancement: support a structured output contract (pipeline string plus policy hints) once the external skill can reliably emit it; v1 remains string-only.
4. Open question: the sparse checkout in `bootstrap_deploy.py` pins branch `feature/sscape-app-skill` and verifies required gstplugins are present. Decide whether a customized pipeline may reference plugins outside that verified set, and reject them during normalization if not.
