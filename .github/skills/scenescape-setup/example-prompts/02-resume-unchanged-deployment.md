<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Resume an unchanged deployment (Fast Path)

Shows the Fast Path for a deployment that already has `deploy-inputs.json`.

## Prompt

```text
Continue the SceneScape deployment in ~/deployments/warehouse-demo — it stopped partway through.
```

## Expected agent behavior

1. `deploy-inputs.json` already exists — skip Step 1 questions, load and show the existing
   `streams`/`camera_ids`/`scene_name` to the user for confirmation (Fast Path).
2. Run the orchestrator with only `--deploy-dir` and `--skill-dir`; `.deploy-state.json` determines
   which step to resume from.
