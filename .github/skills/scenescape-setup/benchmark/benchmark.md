<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: scenescape-setup

**Agents**: Cursor Agent (Task subagents, inherit model)
**Grader**: Cursor Agent (expectation grading per `skill-creator` `agents/grader.md`)
**Date**: 2026-09-16T22:32:39Z
**Evals**: 1, 2, 3, 4, 5 (1 run per configuration)
**Config**: `with_skill` only (harness: read skill + produce dry-run guidance; no real network/services)
**Workspace**: `/tmp/scenescape-setup-eval-20260916-223024`

## Summary

> 100% expectation pass rate with the skill loaded.

### Evals passed

| Agent | w/ skill |
|---|---|
| Cursor Agent | **5 / 5** |

### Pass rate (avg ± σ across evals)

| Agent | w/ skill |
|---|---|
| Cursor Agent | **100% ±0%** |

### Time (total across all evals)

| Agent | w/ skill |
|---|---|
| Cursor Agent | ~385 s (parallel wall ~2 min; sum of per-eval ~77 s mean) |

### Tokens (total across all evals)

| Agent | w/ skill |
|---|---|
| Cursor Agent | n/a (Task notifications did not expose token counts) |

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

- Attempted the guide-recommended `python3 ~/open-edge-platform/skills/tools/run_multi_cli_eval.py --skill-path ...` first. **Blocked**: GitHub Copilot CLI has no auth (`No authentication information found`); Claude Code / Codex CLIs not installed; headless `cursor-agent` requires `CURSOR_API_KEY` / `agent login`.
- Fell back to **skill-creator Stages 5–6** inside this Cursor session: five parallel Task subagents with the with-skill harness prompt (read `SKILL.md` + references; dry-run plan only), then expectation grading against `evals/evals.json`, then `scripts.aggregate_benchmark`.
- Raw run artifacts (responses, transcripts, `grading.json`, `timing.json`, `benchmark.json`) live under `/tmp/scenescape-setup-eval-20260916-223024/iteration-1/`.
- Post-change regression check after coordinate-convention / camera-uid / model-download-retry / model-swap / object-library / FPS-chunking skill updates: all five evals still pass at 100%.
