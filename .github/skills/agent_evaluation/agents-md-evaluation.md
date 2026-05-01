<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Agents.md Evaluation Skill

Use this skill to evaluate any service-level Agents.md file for agent usefulness and quality.

## When To Use

Use this skill when asked to:

- Evaluate, score, review, or audit an Agents.md file.
- Compare quality across multiple service Agents.md files.
- Suggest targeted improvements to raise Agents.md quality.

## Evaluation Objective

Determine whether the target Agents.md is optimized for coding agents and avoids low-value content.

High-value content:

- Service purpose and critical invariants.
- Non-obvious constraints and risk boundaries.
- Measurable KPIs tied to service outcomes.
- Verification expectations for risky edits, with concrete command paths and pass criteria.

Low-value content to penalize:

- Runtime-discoverable inventories (large file trees, endpoint dumps, exhaustive symbol lists).
- Generic stack knowledge commonly known by advanced coding agents.
- "Read these docs first" directives before they are needed.

## Scoring Rubric (0-2 each, max 20)

Score each dimension:

- 0: Missing or poor
- 1: Partial
- 2: Strong and explicit

1. Purpose clarity
2. Non-obvious guidance
3. Actionability
4. KPI quality
5. Signal-to-noise
6. Constraint safety
7. Verification expectations
8. Conciseness (target under 200 lines)
9. Change-risk coverage
10. Audience fit (coding-agent focused)

### Dimension 7 Scoring Notes (Verification Expectations)

Use these anchors when scoring `verification_expectations`:

- **0**: Missing verification section, or no actionable validation instructions.
- **1**: Verification guidance exists but is generic (for example, "run relevant tests") or lacks concrete command paths and explicit pass criteria.
- **2**: Verification gate is standardized and explicit, including:
  - at least one concrete command path per relevant change class (API/schema, algorithm/logic, performance, migrations/persistence), and
  - explicit pass criteria for each class (for example, exit code plus behavioral/metric expectation), and
  - `N/A` explicitly called out only when a class truly does not apply.

## Pass/Fail Rules

- PASS if total_score >= 16 and no dimension score is 0.
- FAIL otherwise.

Hard fail:

- Any dimension score of 0.

## Required Output Format

Return only JSON:

```json
{
  "file": "service/Agents.md",
  "total_score": 0,
  "max_score": 20,
  "status": "PASS|FAIL",
  "dimension_scores": {
    "purpose_clarity": { "score": 0, "evidence": "", "required_fix": "" },
    "non_obvious_guidance": { "score": 0, "evidence": "", "required_fix": "" },
    "actionability": { "score": 0, "evidence": "", "required_fix": "" },
    "kpi_quality": { "score": 0, "evidence": "", "required_fix": "" },
    "signal_to_noise": { "score": 0, "evidence": "", "required_fix": "" },
    "constraint_safety": { "score": 0, "evidence": "", "required_fix": "" },
    "verification_expectations": {
      "score": 0,
      "evidence": "",
      "required_fix": ""
    },
    "conciseness": { "score": 0, "evidence": "", "required_fix": "" },
    "change_risk_coverage": { "score": 0, "evidence": "", "required_fix": "" },
    "audience_fit": { "score": 0, "evidence": "", "required_fix": "" }
  },
  "blocking_issues": [],
  "top_3_improvements": []
}
```

Validation:

- total_score must equal the sum of all dimension scores.
- status must be FAIL if any score is 0.
- status must be FAIL if total_score < 16.

Additional consistency rule:

- If the evaluator recommends adding standardized verification gates with concrete command paths and pass criteria, `verification_expectations` must not be scored `2`.

## Evaluation Procedure

1. Read target Agents.md.
2. Score all 10 dimensions with evidence from the file.
3. Populate required_fix for all dimensions scored < 2.
4. Produce JSON only.

## Prompt Snippet

Use this prompt template when invoking this skill:

```text
Evaluate <TARGET_FILE> using .github/skills/agent_evaluation/agents-md-evaluation.md.
Return only JSON in the required output format from that skill.
Use explicit evidence from the target file content.
```
