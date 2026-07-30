<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: scenescape-setup

Model: copilot=claude-sonnet-5, Date 2026-07-20T17:22:19Z Evals: 1, 2, 3, 4, 5 (1 run(s) each per configuration

## Summary

Evaluated with the multi-CLI eval runner (`skills/tools/run_multi_cli_eval.py`) against
`evals/evals.json`, graded with an LLM judge (Copilot CLI, `claude-sonnet-5`). All 5 evals
now pass **100%** of their expectations with the skill loaded (`with_skill`).

| Eval | Scenario                                | Pass rate  |
| ---- | --------------------------------------- | ---------- |
| 1    | Fresh multi-camera deploy (video files) | 9/9 (100%) |
| 2    | Resume a stopped deployment (Fast Path) | 4/4 (100%) |
| 3    | Redeploy after a camera/stream change   | 4/4 (100%) |
| 4    | Reactive tracker tuning                 | 5/5 (100%) |
| 5    | Reactive Re-ID tuning                   | 5/5 (100%) |

The `without_skill` baseline scores near 0% on the same expectations (no awareness of the
orchestrator, checkpoint files, or tuning references), confirming the skill provides real lift.
