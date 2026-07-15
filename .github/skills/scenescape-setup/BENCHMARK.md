<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark — scenescape-setup

## Status

No automated with-skill / without-skill grading run has been executed yet for this
skill. The scores, pass rates, and token/time comparisons produced by the
skill-creator's Stage 5–6 loop (see `SKILLS_GUIDE.md`) are **not yet available**.

This file will be replaced with generated `benchmark.md` content (pass rate, timing,
and token usage per eval, with-skill vs. baseline) the next time that loop is run
against `evals/evals.json`.

## What has been validated so far (manual review)

- All 4 example prompts in `example-prompts/` were manually walked through against the
  `SKILL.md` file to confirm the described agent behavior matches the actual step
  numbering, flags, and file layout.
- Cross-references between `SKILL.md` → `references/` → `scripts/` were checked for
  broken links after the `examples/` → `example-prompts/` rename and the phase-skill
  merge back into a single skill directory.
- `evals/evals.json` assertions were authored by hand from this manual review; they
  describe expected behavior but have **not** been graded against real with-skill /
  without-skill agent runs.

## How to produce a real benchmark

1. Run the skill-creator (or an equivalent eval harness) against
   `evals/evals.json`, spawning with-skill and baseline runs for each eval case.
2. Grade each assertion and aggregate into `grading.json` / `benchmark.json`.
3. Regenerate this file from `benchmark.json` with pass rate, duration, and token
   usage for with-skill vs. baseline, per eval.
