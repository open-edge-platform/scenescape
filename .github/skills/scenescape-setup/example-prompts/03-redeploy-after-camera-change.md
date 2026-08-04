<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Redeploy after a camera change

Shows the `--fresh` path when cameras/streams change, as opposed to a plain resume.

## Prompt

```text
In ~/deployments/warehouse-demo, replace cam1 with a new camera at
rtsp://192.168.1.15:8554/cam1-new (ID: cam1-new). Redeploy.
```

## Expected agent behavior

1. This changes `streams`/`camera_ids` — treat as a new deployment, not a resume.
2. Re-run Step 1 in full with the new values, then run the orchestrator with `--fresh` (clears
   `.deploy-state.json` and the old `deploy-inputs.json`) before proceeding through all phases.
