<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

## Plan: Migrate Model Downloads to Model Download Microservice

Replace the skill's hardcoded `download_detection_models.sh` / `check_detection_models.sh` pair
(which fetches `person-detection-retail-0013` directly from `storage.openvinotoolkit.org`) with the
[Model Download Microservice](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/model-download)
ephemeral container path. The migration makes the detection model configurable, removes the hard
dependency on the Open Model Zoo bucket, and aligns SceneScape's model acquisition with the
shared Open Edge Platform model-download ecosystem.

Basic deployments that omit a `model_id` input continue using the current default model
(`person-detection-retail-0013`) fetched via the existing script during a transitional period;
switching to the microservice path is gated on the user supplying a supported hub and model name.

**Status (2026-08-04)**: Phase 2's core mechanism is implemented — `download_detection_models.sh`
was deleted; the orchestrator (`deploy_scenescape.sh`) and all docs now call
`scripts/download_model.py` directly, which drives the real `intel/model-download` container's
REST API (`POST /api/v1/models/download`, poll `GET /api/v1/jobs`), matching the mechanism the
rest of the repo now uses (`model_download/Makefile` + `model_download/src/download_models.py`)
since the model-installer removal (commit `20ef4a2a`, "Switching downloading models to
model-download tool"). `check_detection_models.sh` was also updated to verify against
`alpine:3.23` instead of the now-deleted `scenescape-model-installer` image. **Not yet done**:
Phases 1, 3, 4, and 6 below — `download_model.py` is still hardcoded to
`person-detection-retail-0013`/`omz` (no `model_id`/`model_hub` input, no legacy fallback branch,
no configurable pipeline model path) — these remain future work if/when configurable-model
support is prioritized.

**Steps**

1. Phase 1 — Input model extension
   - Extend `deploy-inputs.json` schema (in `scripts/deploy_inputs.py`) with optional fields:
     `model_id`, `model_hub` (one of `huggingface`, `ultralytics`, `pipeline-zoo-models`, etc.),
     and `model_precision` (default `FP32`). Leave all existing keys untouched.
   - Update `inputs_match()` to include the new fields in the consistency check so that a model
     change on resume is detected and flagged, consistent with how stream/camera changes are handled.
   - Update Step 1 in `SKILL.md` to ask for the optional model fields and document when the
     microservice path is taken vs. the legacy path.

2. Phase 2 — Model download script replacement **[DONE, unconditional path only]**
   - `scripts/download_model.py` was added. It always invokes the Model Download Microservice
     REST API for `person-detection-retail-0013`/`omz` — there is no `model_id`/`model_hub` input
     yet (that's Phase 1, still pending), so there is no legacy-vs-microservice branch to take.
   - The ephemeral container path requires no persistent service: `download_model.py` starts the
     `intel/model-download` container, requests the download, polls jobs to completion, then
     always stops/removes the container — a one-shot run per invocation, matching the previous
     behavior of `download_detection_models.sh`.
   - The idempotency check (skip download if model already present) is preserved — it now checks
     via an `alpine:3.23` container instead of the deleted `scenescape-model-installer` image.
   - `download_detection_models.sh` was **deleted** (it had become a pure pass-through wrapper
     with no logic of its own once `download_model.py` existed, so keeping it added indirection
     with no benefit). The orchestrator and every doc reference were updated to call
     `scripts/download_model.py` directly instead.
   - **Remaining for a full Phase 2**: implement the `model_id`/`model_hub`-gated legacy fallback
     once Phase 1 lands (today there is nothing to fall back *from*, since the only path is the
     microservice call).

3. Phase 3 — Pipeline config generalization
   - Update `scripts/adapt_pipeline_config.py` to read `model_id` from `deploy-inputs.json`
     (defaulting to `omz/person-detection-retail-0013/FP32/person-detection-retail-0013.xml`)
     and substitute it into the GStreamer pipeline string, removing the hardcoded model path.
   - Update `references/pipeline-config.md` to document the configurable model field alongside
     the existing pipeline spec.

4. Phase 4 — Health check generalization **[partially done]**
   - `references/runtime-verification.md` troubleshooting row now mentions `download_model.py`
     alongside `download_detection_models.sh` — **done**.
   - Still pending: `scripts/check_detection_models.sh` still hardcodes
     `omz/person-detection-retail-0013/FP32/...`; accepting the model path as an argument is
     blocked on Phase 1/3 (no configurable model path exists yet to pass in).

5. Phase 5 — Skill documentation **[partially done]**
   - `references/pipeline-config.md`'s "Planned" bullet about `download_detection_models.sh`
     being replaced — **updated** to describe the now-implemented microservice call instead of a
     future plan.
   - `SKILL.md` step 7 prose — **updated** to describe `download_model.py`'s REST flow.
   - `references/phase-bootstrap.md` does not name `download_detection_models.sh` directly (only
     generic "model downloads" prose) — no change needed there.
   - Still pending: `SKILL.md` Step 1 inputs table has no model fields yet (depends on Phase 1).
   - Still pending: add or reference the `model-download-user` skill from the Model Download
     Microservice repo for users who want to manage models independently of the deployment flow:
     `https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/model-download/.github/skills/model-download-user`

6. Phase 6 — Verification plan **[not started]**
   - Static validation: `bash -n` and `python3 -m py_compile` were run against the three touched
     scripts (pass) — full lint targets and `skillspector scan` have not been run yet.
   - Behavioral validation (end-to-end deploy exercising `download_model.py` against a live
     `intel/model-download` container, idempotency re-run, and resume-after-checkpoint) has not
     been performed — no Docker deployment was run in this session.
   - Since there is only one path now (no `model_id` input yet), validations A/B from the
     original plan collapse into a single "microservice path" check once Phase 1 lands.

**Relevant files**

Paths are repo-relative to the SceneScape checkout.

- `.github/skills/scenescape-setup/SKILL.md` — step 7 prose updated **[done]**; Step 1 inputs table model fields still pending Phase 1.
- `.github/skills/scenescape-setup/references/pipeline-config.md` — "Planned" note updated to reflect the implemented call **[done]**.
- `.github/skills/scenescape-setup/references/runtime-verification.md` — model-missing troubleshooting row updated **[done]**.
- `.github/skills/scenescape-setup/references/phase-bootstrap.md` — reviewed; no `download_detection_models.sh` name reference to update **[done, no-op]**.
- `.github/skills/scenescape-setup/scripts/deploy_inputs.py` — add `model_id`, `model_hub`, `model_precision` fields. **[pending, Phase 1]**
- `.github/skills/scenescape-setup/scripts/download_model.py` — new: calls the Model Download Microservice REST API. **[done]**; legacy-fallback branch still pending Phase 1.
- `.github/skills/scenescape-setup/scripts/adapt_pipeline_config.py` — read `model_id` from inputs instead of hardcoding. **[pending, Phase 3]**
- `.github/skills/scenescape-setup/scripts/check_detection_models.sh` — now checks via `alpine:3.23` **[done]**; accept model path as argument **[pending, Phase 4]**.
- `.github/skills/scenescape-setup/scripts/download_detection_models.sh` — **deleted**; it had
  become a pure pass-through wrapper around `download_model.py` with no logic of its own, so it
  was removed and every caller updated to invoke `download_model.py` directly. **[done]**
- `.github/skills/scenescape-setup/evals/evals.json` — add or extend an eval covering a non-default model deployment. **[pending, Phase 6]**

**Decisions**

- The migration uses the Model Download Microservice's **REST API against an ephemeral
  container** (start container → `POST /api/v1/models/download` → poll `GET /api/v1/jobs` →
  stop container), matching `model_download/Makefile`'s `install-models` target, rather than a
  long-running service — this preserves parity with the previous one-shot download behavior.
- **Revised**: there is no legacy OMZ-bucket-curl fallback anymore — `download_model.py`
  unconditionally uses the microservice, since the OMZ hub is fully supported by
  `intel/model-download` (see Further Considerations #1 below, which corrects the original
  plan's assumption). The "legacy path preserved until validated" decision from the original
  plan was dropped in favor of a direct replacement, since the old OMZ bucket approach had no
  advantage over the now equally-OMZ-capable microservice.
- `download_detection_models.sh` was deleted once it became a no-op wrapper around
  `download_model.py`; `deploy_scenescape.sh` and all skill docs now call
  `python3 scripts/download_model.py <deploy_dir>` directly.
- The detection model path in `adapt_pipeline_config.py` / `check_detection_models.sh` is still
  hardcoded to `person-detection-retail-0013` pending Phase 1/3/4 (configurable `model_id`).
- The `model-download-user` skill is referenced but not embedded; agents needing detailed
  model-download guidance should load that skill directly.

**Further Considerations**

1. ~~Model zoo coverage: the Model Download Microservice does not currently support the Open
   Model Zoo bucket~~ — **this was incorrect.** `model_download/models.json` (the repo's actual
   model list post-migration) uses `hub: "omz"` for every entry, and
   `model_download/Makefile`'s default `MODEL_DOWNLOADER_CMD` is `--plugins omz`. OMZ is fully
   supported; `download_model.py` uses it directly for `person-detection-retail-0013` with no
   fallback needed.
2. Volume layout: `download_model.py` downloads into `<project>_vol-models` at
   `/opt/models` inside the `intel/model-download` container (matching
   `model_download/Makefile`'s `-v "$(MODEL_VOLUME)":/opt/models`), landing at the same
   `omz/person-detection-retail-0013/FP32/...` path the DL Streamer pipeline server container
   expects under `/models` — confirmed by inspecting `model_download/Makefile` and
   `model_download/models.json`; not verified against a live deployment in this session.
3. Integrity verification: the old `download_detection_models.sh` verified SHA256 checksums
   after a raw curl download. `download_model.py` does not re-implement checksum verification —
   integrity is now the `intel/model-download` microservice's responsibility (same trust
   boundary the rest of the repo's `model_download/` tooling relies on); this is an intentional
   scope reduction, not an oversight.
