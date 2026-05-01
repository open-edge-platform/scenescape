---
agent: agent
name: agent-evaluation
title: Agent Evaluation Skills
description: Evaluate and empirically test service Agents.md files for quality and behavioral impact.
tags:
  - agents-md
  - evaluation
  - scoring
  - efficacy
  - review
triggers:
  - evaluate Agents.md
  - score Agents.md
  - review Agents.md
  - audit Agents.md
  - test efficacy of Agents.md
  - empirically evaluate Agents.md
  - run efficacy trials for Agents.md
  - measure Agents.md usefulness
---

<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Agent Evaluation Skills

This skill covers two capabilities:

| Ask                                                         | Action                                                                                                                                                                   |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Evaluate / score / review / audit an Agents.md              | Load `agents-md-evaluation.md`, score it, then **automatically continue to the Efficacy Test if the result is PASS** unless the user explicitly asks for rubric-only output |
| Empirically test / measure usefulness / run efficacy trials | Prerequisite gate must be run first; if PASS, follow the Efficacy Test procedure below                                                                                   |

For rubric evaluation, load `agents-md-evaluation.md` first and follow it exactly.
For efficacy testing, the rubric must PASS before proceeding — see Prerequisite below.

> **Default behavior**: When a user asks to "evaluate" an Agents.md without
> qualifying the scope, run the rubric gate AND the efficacy test in sequence.
> Stop between stages only if the rubric result is FAIL. Do not ask for
> confirmation to proceed from gate to efficacy test on a PASS result.

---

# Agents.md Efficacy Test

Use this procedure to measure whether a service Agents.md actually improves coding-agent output quality via controlled trials. This is distinct from the rubric-scoring approach in `agents-md-evaluation.md`, which scores document quality. This procedure scores behavioral impact.

## When To Use

Use this when asked to:

- Empirically test or measure whether an Agents.md is useful in practice.
- Produce evidence comparing agent outputs with and without an Agents.md.
- Validate that Agents.md content justifies its maintenance cost.

## Methodology

### Overview

Run controlled, blind subagent trials: each agent receives either the full Agents.md (WITH) or a minimal service stub (WITHOUT). Compare outputs against a scoring rubric derived from the Agents.md content and service understanding.

- 3 task types covering representative change classes.
- 5 trial framings per task per condition (vary the ask style to produce genuine output variance).
- Total: 30 trials per service evaluated.

All trials must be self-contained: agents answer from provided context only — no file browsing.

### Prerequisite — Run the Rubric Gate

Before running any efficacy trials, evaluate the target Agents.md using `agents-md-evaluation.md` (in this same folder).

- If the result is **PASS** (total_score ≥ 16 and no dimension score is 0): **immediately continue to Step 1 without waiting for user confirmation**.
- If the result is **FAIL**: stop. Report the rubric scores and required fixes. Do not run efficacy trials on a failing Agents.md — low-quality input will produce misleading efficacy results. Fix the document first, re-run the rubric, then return here.

### Step 1 — Read the target Agents.md and understand the service

Load and record from the Agents.md:

- All Non-Obvious Constraints
- All KPI targets with numeric values
- All When-Editing conditions
- The Verification Gate table (full command paths and pass criteria)

Also gather enough understanding of the service from the codebase to distinguish constraints that are **non-obvious** (not derivable from general engineering knowledge or the service's plain-language description) from those that are **general** (apply to any similar service). This distinction drives Step 5.

### Step 2 — Select 3 representative tasks

Choose one task from each of these categories:

| Category                        | Guidance                                                                                                                                                        |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Feature addition                | A concrete change that touches the service's inbound data contract (e.g., new optional field, new message type, schema extension)                               |
| Performance optimization        | A change targeting one of the service's named KPI targets by name and threshold as stated in the Agents.md                                                      |
| Risky / safety-sensitive change | A change that tempts bypassing a constraint explicitly stated in the Agents.md (e.g., skipping validation, removing a safety boundary, weakening a trust check) |

Tasks must be concrete and service-specific, not generic. Reference specific KPI names and thresholds from the Agents.md. Do not reuse the controller example tasks from the results file.

### Step 3 — Design 5 trial framings per task

For each task, create 5 prompt variants that frame the same problem differently:

1. Direct implementation request ("Describe what changes you would make…")
2. Peer review framing ("A colleague has proposed X. Review the approach…")
3. Design proposal request ("Write a brief design proposal covering schema, code, and verification…")
4. Pitfall analysis ("What would a naive developer get wrong when doing X?")
5. Risk and evidence framing ("Outline risks and what the PR must include to be accepted")

### Step 4 — Construct prompts

**WITH prompt structure:**

```
You are a coding agent. Answer based ONLY on the context below — do not browse any files.

SERVICE GUIDE (<service>/Agents.md):
---
<full Agents.md content here>
---

TASK: <task framing text>
```

**WITHOUT prompt structure:**

```
You are a coding agent. Answer based ONLY on the context below — do not browse any files.

SERVICE CONTEXT (no service guide provided):
<one-paragraph description of what the service does — no constraints, no KPIs>

TASK: <same task framing text>
```

### Step 5 — Derive scoring criteria from the Agents.md and service understanding

Do not use a fixed standard set of criteria. Instead, generate 5 binary criteria specific to the target Agents.md and service, using the following process:

**Process:**

1. Re-read the Non-Obvious Constraints, KPI targets, When-Editing conditions, and Verification Gate from Step 1.
2. Identify which constraints and requirements are **non-obvious** — things an agent working from a plain-language service description alone would not produce. These become C4 and C5.
3. Identify which requirements are **structurally important but general** — things any well-engineered similar service would need (e.g., backward compat, validation at boundaries). These become C1–C3.
4. Assign exactly one criterion per slot. Every criterion must have a binary, evidence-based hit definition.

**Slot guidance:**

| Slot | What it should test                                                                                                       | Hit definition rule                                                                                  |
| ---- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| C1   | The most critical safety or correctness boundary for this service                                                         | Must be explicitly mentioned, not implied                                                            |
| C2   | Contract or interface stability (general but essential)                                                                   | Requires explicit preservation language or optionality                                               |
| C3   | A service-specific operational discipline stated in the Agents.md (e.g., hot-path rules, ordering rules, resource limits) | Must cite the specific discipline, not generic advice                                                |
| C4   | Use of the Verification Gate — concrete test commands                                                                     | Must name an actual command path or rebuild step, not "run your tests"                               |
| C5   | Non-obvious constraint awareness — something only in the Agents.md                                                        | Must cite a value, constraint name, or invariant that is absent from any generic service description |

**Rules:**

- C5 is the most important criterion. It directly measures the unique value of the Agents.md. If you cannot identify at least one genuinely non-obvious constraint, the Agents.md likely needs improvement before efficacy testing.
- A criterion hit requires explicit evidence in the output — not advice that could apply to any service of the same type.
- Write the hit definition precisely enough that two independent scorers would agree on each trial.
- Record the derived criteria before running trials so they are fixed for all 30 outputs.

### Step 6 — Run trials

Fire all 30 subagent prompts. Run WITH and WITHOUT trials in parallel where possible. Each subagent must:

- Have no access to the workspace.
- Answer entirely from the provided context.
- Produce a response to a single task framing.

### Step 7 — Score all outputs

For each of the 30 outputs, apply all 5 binary criteria. Record the score as a table.

Rules:

- A criterion hit requires explicit evidence in the output — not generic advice that could apply to any service.
- C5 in particular requires citing a service-specific value, name, or constraint that only appears in the Agents.md.
- Score independently per framing; do not average across framings before recording.

### Step 8 — Report results

Produce the following in the result:

1. Per-trial score table for each task (WITH vs WITHOUT × 5 trials × 5 criteria).
2. Per-task averages (WITH avg and WITHOUT avg).
3. Per-criterion hit rate across all 15 trials per condition.
4. Overall hit rate WITH vs WITHOUT.
5. Key findings in plain language, stating which criteria show the largest gap and why.

## Interpreting Results

| Overall hit rate WITH | Interpretation                                                                                      |
| --------------------- | --------------------------------------------------------------------------------------------------- |
| ≥ 90%                 | Agents.md is highly effective — content surfaces consistently.                                      |
| 70–89%                | Agents.md is useful but has gaps; review which criteria fail most.                                  |
| < 70%                 | Agents.md content is not reliably reaching agents; revise non-obvious constraints and KPI sections. |

| Gap (WITH − WITHOUT) | Interpretation                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| ≥ +40 pp             | Strong evidence Agents.md adds unique value beyond general knowledge.                             |
| +20–39 pp            | Moderate value; worth maintaining.                                                                |
| < +20 pp             | Low marginal value; Agents.md may be stating general knowledge. Remove or replace those sections. |

If C5 (non-obvious constraint awareness) gap is small, the Agents.md is likely repeating general engineering advice rather than encoding service-specific invariants. Prioritize adding non-obvious constraints and specific KPI targets.

## Confounds To Watch For

- **System-prompt leakage**: If the system prompt includes architectural notes about the service (e.g., from `copilot-instructions.md`), WITHOUT trials may accidentally receive service context. Score C5 conservatively — only count a hit where the specific value or constraint was absent from every system-prompt source, not just the Agents.md.
- **Framing bias**: Risky-change framings (task category 3) tend to produce general security rejections even without the guide. Record the verdict (accept/reject) separately from quality. The guide's unique contribution in risky-change tasks is specific KPI citations and constraint-grounded alternatives, not the rejection itself.
- **High-knowledge tasks**: Some task types (e.g., performance optimization) score higher WITHOUT because the underlying discipline is widely known. Identify this pattern per-criterion in your findings and distinguish general knowledge (low gap) from Agents.md-specific knowledge (high gap).
- **Criteria drift**: Because criteria are derived per-service, ensure they are recorded and fixed before trials are scored. Do not adjust criteria after seeing trial outputs.

## Example Results Table Format

```
| Trial    | C1 | C2 | C3 | C4 | C5 | Score |
|----------|----|----|----|----|----|-------|
| WITH-1   |  ✓ |  ✓ |  ✓ |  ✓ |  ✓ |  5/5  |
| WITH-2   |  ✓ |  ✓ |  ✓ |  ✓ |  ✓ |  5/5  |
| WITHOUT-1|  ✓ |  ✓ |  ✗ |  ✗ |  ✗ |  2/5  |
| WITHOUT-2|  ✓ |  ✗ |  ✗ |  ✗ |  ✗ |  1/5  |
| With avg |    |    |    |    |    |  5.0  |
| W/O avg  |    |    |    |    |    |  1.5  |
```
