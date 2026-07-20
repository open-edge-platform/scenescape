<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

## Plan: Integrate DLS Pipeline Configurator

Add a new optional pipeline-configuration phase to scenescape-setup that invokes the external dlstreamer-coding-agent only when the user provides a customization prompt, consumes a single generated GStreamer pipeline string, adapts it into SceneScape-compatible pipeline-config.json entries (timestamping, metaconvert, policy constraints, adapter kwargs), and then continues existing deployment gates. Keep current defaults for basic deployments and fail fast only when customization is requested and cannot be satisfied by defaults.

**Steps**

1. Phase 1: Discovery hardening and interface contract
1. Define the external invocation contract in scenescape-setup references: required input payload (camera_ids, streams, user prompt, optional model/device hints), expected output (single pipeline string), and error shape.
1. Add explicit guardrail that external skill invocation is conditional: run only when a new user input field (pipeline_customization_prompt) is non-empty. If empty, preserve current adapt_pipeline_config flow. _blocks all later logic_
1. Decide invocation mechanism abstraction (remote command wrapper) so setup scripts do not hardcode network/repo assumptions. Add environment-configurable command path and timeout/retry behavior. _depends on previous step_
1. Phase 2: Setup input model updates
1. Extend deploy input persistence in .github/skills/scenescape-setup/scripts/deploy_inputs.py to include optional pipeline_customization_prompt and optional pipeline_customization_mode metadata.
1. Update .github/skills/scenescape-setup/SKILL.md and phase skill docs to require asking for the optional prompt during Step 1 and to document when external invocation occurs. _parallel with next step_
1. Update argument parsing and resume semantics in .github/skills/scenescape-setup/scripts/deploy_scenescape.sh so prompt state is loaded from deploy-inputs.json on resume and compared in consistency checks. _depends on deploy_inputs.py changes_
1. Phase 3: Pipeline configurator skill and script
1. Add new skill folder .github/skills/scenescape-setup-pipeline-config with SKILL.md describing step purpose, prerequisites, and failure handling.
1. Add a new script .github/skills/scenescape-setup/scripts/configure_pipeline.py that:
1. Reads generated pipeline-config.json from deploy dir.
1. If prompt missing: no-op with explicit log that defaults are retained.
1. If prompt present: invokes external dlstreamer-coding-agent wrapper and obtains one pipeline string.
1. Validates string contains required SceneScape-compatible elements or can be normalized.
1. Applies/normalizes SceneScape requirements: rtspsrc timestamp metadata support, gvametaconvert add-tensor-data=true, gvapython adapter module/class/function names, payload camera_config consistency, policy whitelist for v1 (detectionPolicy, reidPolicy, classificationPolicy).
1. Writes updated per-camera pipeline entries while keeping DLS config envelope structure unchanged.
1. Add strict validation + fail-fast behavior only for customized mode when generated pipeline cannot be normalized and defaults cannot satisfy request.
1. Phase 4: Orchestrator step integration
1. Insert a new step in .github/skills/scenescape-setup/scripts/deploy_scenescape.sh between current bootstrap and warmup gates (new step 7), then renumber downstream step state bookkeeping and phase boundaries.
1. Add a new phase selector value pipeline_config in phase_start_step/phase_end_step and include it in usage/help text.
1. Ensure existing phases still map correctly:
1. bootstrap now ends after pipeline configuration.
1. calibrate and scene start-step logic reflects renumbering.
1. resume logic and .deploy-state.json compatibility remain intact.
1. Phase 5: Policy and schema consistency safeguards
1. In configure_pipeline.py, validate metadatagenpolicy against adapter-supported policies from dlstreamer-pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py and reject unsupported policy names.
1. Add schema-aware checks so modified payload fields still conform to parameter schema shape emitted by adapt_pipeline_config.py.
1. Keep camera-data compatibility assumptions explicit (do not alter MQTT payload contract in this task).
1. Phase 6: Documentation updates
1. Update .github/skills/scenescape-setup/SKILL.md:
1. Step map includes new step 7 pipeline-configurator.
1. Inputs table includes optional pipeline customization prompt.
1. Phased sub-skill table includes scenescape-setup-pipeline-config.
1. Update .github/skills/scenescape-setup-bootstrap/SKILL.md to reflect revised step range.
1. Update .github/skills/scenescape-setup-calibrate/SKILL.md and .github/skills/scenescape-setup-scene/SKILL.md step numbers only where required.
1. Update .github/skills/scenescape-setup/references/pipeline-config.md with new conditional generation path and normalization rules.
1. Add user-guide docs under docs/user-guide/other-topics if setup behavior is user-visible beyond skill docs.
1. Phase 7: Verification plan
1. Static validation: run shell and python lint/format checks used by repository standards for touched files.
1. Behavioral validation A (default mode): run bootstrap flow without prompt and verify generated pipeline-config.json is unchanged from baseline behavior.
1. Behavioral validation B (custom mode success): provide prompt requesting reid/classification policy; verify configure step updates pipeline string and payload policy while preserving timestamp and metaconvert requirements.
1. Behavioral validation C (custom mode failure): provide incompatible prompt and verify deployment stops at pipeline configuration step with actionable error.
1. Resume/regression validation: checkpoint after step 6, rerun with --resume and ensure step 7 executes correctly; verify phase pipeline_config can run in isolation.

**Relevant files**

- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup/SKILL.md — add optional prompt input, step map changes, sub-skill links.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup-bootstrap/SKILL.md — adjust phase scope and invocation guidance.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup-calibrate/SKILL.md — step-number alignment after insertion.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup-scene/SKILL.md — step-number alignment and prerequisites text.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup/scripts/deploy_scenescape.sh — new step function, renumbering, phase mapping, resume behavior.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup/scripts/deploy_inputs.py — persist/validate optional customization prompt.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup/scripts/adapt_pipeline_config.py — keep baseline defaults path; optionally expose reusable helpers for configure script.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup/scripts/configure_pipeline.py — new customization + external invocation orchestrator.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/.github/skills/scenescape-setup/references/pipeline-config.md — document dual path (default/customized) and policy constraints.
- /home/spoluri/open-edge-platform/geospatial-map/scenescape/dlstreamer-pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py — source of truth for supported metadata policies to validate against.

**Verification**

1. Run targeted script-level checks for .github/skills/scenescape-setup/scripts/deploy_inputs.py, .github/skills/scenescape-setup/scripts/configure_pipeline.py, and .github/skills/scenescape-setup/scripts/adapt_pipeline_config.py.
1. Execute orchestrator in bootstrap phase without prompt and confirm no behavioral drift in pipeline-config.json.
1. Execute new pipeline_config phase with a prompt and confirm per-camera pipeline entries are updated and valid.
1. Validate fail-fast path by using a prompt that requests unsupported policy output; confirm non-zero exit and clear diagnostics.
1. Validate resume and phase boundaries by replaying from checkpoint with --resume and --phase pipeline_config.

**Decisions**

- External invocation is conditional, not mandatory.
- Contract from external agent is a single GStreamer pipeline string.
- v1 supported policies are detectionPolicy, reidPolicy, classificationPolicy.
- Failure behavior: if user requested customization and defaults cannot satisfy request, stop deployment.
- Basic deployments continue using adapt_pipeline_config defaults with no external dependency.

**Further Considerations**

1. Invocation transport recommendation: implement a thin adapter command interface first (environment-driven command + JSON stdin/stdout) to avoid coupling setup skill logic to one remote execution path.
2. Compatibility recommendation: keep configure_pipeline.py strictly additive to pipeline-config.json and avoid changing tracker/schema payload structure in this iteration.
3. Future enhancement: add structured output contract support (pipeline string + policy hints) once external skill can reliably emit it; current v1 remains string-only per decision.
