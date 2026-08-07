<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: scenescape-setup

**Model**: gpt-5.6-terra
**Date**: 2026-08-07T02:46:09Z
**Evals**: 1, 2, 3, 4, 5 (1 run(s) each per configuration)

## Summary

> **How to read this table** -- **Avg** is the mean score across all evals; **Std Dev** (the +/- spread) measures how much individual evals varied around that average -- small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with - without).

| Metric | Avg +/- Std Dev (With Skill) | Avg +/- Std Dev (Without Skill) | Skill Lift (Delta) |
|--------|-------------------------------|----------------------------------|--------------------|
| Pass Rate (% correct) | 100% avg, +/-0% spread (consistent) | 2% avg, +/-5% spread (unreliable) | +98pp |
| Time (s / question) | 24.9s avg, +/-3.2s spread (consistent) | 12.1s avg, +/-3.9s spread (variable) | +12.8s |
| Tokens (context cost) | 135k avg, +/-22k spread (variable) | 20k avg, +/-522 spread (consistent) | +114k |
