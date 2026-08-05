<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

## Plan: Migrate Model Downloads to Model Download Microservice

Replace the skill's hardcoded `download_detection_models.sh` / `check_detection_models.sh` pair
(which fetches `person-detection-retail-0013` directly from `storage.openvinotoolkit.org`) with the
[Model Download Microservice](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/model-download)
ephemeral container path. The migration makes the detection model configurable, removes the hard
dependency on the Open Model Zoo bucket, and aligns SceneScape's model acquisition with the
shared Open Edge Platform model-download ecosystem.

Basic deployments that omit a `model_id` input continue using the current default model
(`person-detection-retail-0013`) fetched via the existing script during a transitional period;
switching to the microservice path is gated on the user supplying a supported hub and model name.

**Steps**

1. Phase 1 — Input model extension
   - Extend `deploy-inputs.json` schema (in `scripts/deploy_inputs.py`) with optional fields:
     `model_id`, `model_hub` (one of `huggingface`, `ultralytics`, `pipeline-zoo-models`, etc.),
     and `model_precision` (default `FP32`). Leave all existing keys untouched.
   - Update `inputs_match()` to include the new fields in the consistency check so that a model
     change on resume is detected and flagged, consistent with how stream/camera changes are handled.
   - Update Step 1 in `SKILL.md` to ask for the optional model fields and document when the
     microservice path is taken vs. the legacy path.

2. Phase 2 — Model download script replacement
   - Add `scripts/download_model.py` that:
     - If `model_id`/`model_hub` are absent from `deploy-inputs.json`, falls back to calling
       the existing `download_detection_models.sh` (legacy path, no behavioral change).
     - If `model_id`/`model_hub` are present, invokes the Model Download Microservice ephemeral
       one-liner (`get_model.sh`) or its REST API to fetch the model into the compose models
       volume, then verifies the file exists at the expected path.
   - The ephemeral container path requires no persistent service: run as a one-shot container that
     exits when the download completes, matching the existing behavior of `download_detection_models.sh`.
   - Preserve the idempotency check (skip download if model already present).
   - Delete `download_detection_models.sh` once the new script is validated and the legacy path
     is confirmed working through it.

3. Phase 3 — Pipeline config generalization
   - Update `scripts/adapt_pipeline_config.py` to read `model_id` from `deploy-inputs.json`
     (defaulting to `omz/person-detection-retail-0013/FP32/person-detection-retail-0013.xml`)
     and substitute it into the GStreamer pipeline string, removing the hardcoded model path.
   - Update `references/pipeline-config.md` to document the configurable model field alongside
     the existing pipeline spec.

4. Phase 4 — Health check generalization
   - Update `scripts/check_detection_models.sh` to accept the model path as an argument
     (defaulting to the current Open Model Zoo path) so it can verify any model downloaded via
     the new path.
   - Update `references/runtime-verification.md` — the troubleshooting row that references
     `download_detection_models.sh` by name should reference `download_model.py` instead.

5. Phase 5 — Skill documentation
   - Update `references/pipeline-config.md`: remove or update the `## Future Work` section
     added as a placeholder; replace with the completed migration notes.
   - Update `SKILL.md` Step 1 inputs table and the reference-lookup table.
   - Update `references/phase-bootstrap.md` if it references the old script.
   - Add or reference the `model-download-user` skill from the Model Download Microservice repo
     for users who want to manage models independently of the deployment flow:
     `https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/model-download/.github/skills/model-download-user`

6. Phase 6 — Verification plan
   - Static validation: run Python and shell lint targets for touched files.
   - Security re-scan: run `skillspector scan .github/skills/scenescape-setup --no-llm`.
     Review any new findings introduced by `download_model.py`.
   - Behavioral validation A (legacy path): deploy with no `model_id` in `deploy-inputs.json`
     and confirm `person-detection-retail-0013` is downloaded as before.
   - Behavioral validation B (microservice path): deploy with a supported `model_id`/`model_hub`
     and confirm the correct model lands in the volume and the pipeline config references it.
   - Behavioral validation C (idempotency): run the download step twice; confirm the second
     invocation detects the model is present and exits cleanly.
   - Resume validation: checkpoint after the model download step; re-run with `--resume` and
     confirm no re-download occurs.

**Relevant files**

Paths are repo-relative to the SceneScape checkout.

- `.github/skills/scenescape-setup/SKILL.md` — optional model fields in Step 1 inputs table.
- `.github/skills/scenescape-setup/references/pipeline-config.md` — configurable model path, remove Future Work placeholder.
- `.github/skills/scenescape-setup/references/runtime-verification.md` — update model-missing troubleshooting row.
- `.github/skills/scenescape-setup/references/phase-bootstrap.md` — update if it names `download_detection_models.sh`.
- `.github/skills/scenescape-setup/scripts/deploy_inputs.py` — add `model_id`, `model_hub`, `model_precision` fields.
- `.github/skills/scenescape-setup/scripts/download_model.py` — new: unified download entrypoint with legacy fallback.
- `.github/skills/scenescape-setup/scripts/adapt_pipeline_config.py` — read `model_id` from inputs instead of hardcoding.
- `.github/skills/scenescape-setup/scripts/check_detection_models.sh` — accept model path as argument.
- `.github/skills/scenescape-setup/scripts/download_detection_models.sh` — delete once `download_model.py` is validated.
- `.github/skills/scenescape-setup/evals/evals.json` — add or extend an eval covering a non-default model deployment.

**Decisions**

- The migration uses the Model Download Microservice **ephemeral container** path (`get_model.sh`),
  not the long-running service, to preserve parity with the current one-shot download behavior.
- Legacy path (`download_detection_models.sh`) is preserved through `download_model.py` until
  the new path is validated end-to-end; no behavior change for deployments that omit `model_id`.
- The detection model path in `adapt_pipeline_config.py` becomes configurable but retains the
  current default so existing deployments are unaffected.
- The `model-download-user` skill is referenced but not embedded; agents needing detailed
  model-download guidance should load that skill directly.

**Further Considerations**

1. Model zoo coverage: the Model Download Microservice does not currently support the Open Model
   Zoo bucket (`storage.openvinotoolkit.org`). The legacy script remains as the fallback for
   `person-detection-retail-0013` until an equivalent model is available via a supported hub
   (e.g. Ultralytics YOLO or a HuggingFace person-detection model).
2. Volume layout: confirm that models downloaded via the microservice land under the same
   `/models/` path expected by the DL Streamer pipeline server container.
3. SHA256 verification: `download_detection_models.sh` verifies checksums after download;
   `download_model.py` should apply equivalent verification for non-legacy paths.
