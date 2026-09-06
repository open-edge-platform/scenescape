<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: scenescape-setup

**Agents**: Cursor Agent (`gpt-5.3-codex`)
**Grader**: Cursor Agent (`gpt-5.3-codex`)
**Date**: 2026-08-14T16:05:46Z
**Evals**: 1, 2, 3, 4, 5 (1 run per configuration)
**Config**: `with_skill` only (harness: read skill + produce dry-run guidance; no real network/services)
**Workspace**: `/tmp/scenescape-setup-eval-20260814-090411`

## Summary

> 100% expectation pass rate with the skill loaded.

### Evals passed

| Agent | w/ skill |
|---|---|
| Cursor Agent (`gpt-5.3-codex`) | **5 / 5** |

### Pass rate (avg ± σ across evals)

| Agent | w/ skill |
|---|---|
| Cursor Agent (`gpt-5.3-codex`) | **100% ±0%** |

### Time (total across all evals)

| Agent | w/ skill |
|---|---|
| Cursor Agent (`gpt-5.3-codex`) | 212 s |

### Tokens (total across all evals)

| Agent | w/ skill |
|---|---|
| Cursor Agent (`gpt-5.3-codex`) | n/a (CLI did not expose token counts) |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses.

| Eval | Prompt | Cursor (w/) |
|---|---|---|
| 1 | Deploy SceneScape in ~/deployments/retail-demo with scene name 'Retail... | PASS (10/10) |
| 2 | Continue the SceneScape deployment in ~/deployments/warehouse-demo — i... | PASS (5/5) |
| 3 | In ~/deployments/warehouse-demo, replace cam1 with a new camera at rts... | PASS (4/4) |
| 4 | The SceneScape deployment in ~/deployments/warehouse-demo is up, but t... | PASS (4/4) |
| 5 | The SceneScape deployment in ~/deployments/retail-demo is up, but the ... | PASS (4/4) |
| | **Mean ±σ** | **100% ±0%** |

## Notes

- Copilot CLI (`@github/copilot`) is installed but blocked by org Copilot policy; Claude Code and Codex CLIs are installed but not authenticated. Eval runs used authenticated Cursor Agent (`cursor-agent -p --mode ask`) with the same with-skill harness prompt shape as `~/mainline/skills/tools/run_multi_cli_eval.py`.
- Skill guidance was tightened after iteration-1 failures so agents emit required exact phrases (watcher `RESULT=` notify, Post-task metrics categories, `.deploy-state.json` resume sentence, `--fresh` full-phase re-exec sentence) and so reactive tuning responses include both the questionnaire and deployed-path JSON edits + scene-only restart in one turn.
