<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: scenescape-setup

**Model**: gpt-5.6-terra
**Date**: 2026-08-06T22:33:32Z
**Evals**: 1, 2, 3, 4, 5 (1 run(s) each per configuration)

## Summary

> **How to read this table** -- **Avg** is the mean score across all evals; **Std Dev** (the +/- spread) measures how much individual evals varied around that average -- small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with - without).

| Metric | Avg +/- Std Dev (With Skill) | Avg +/- Std Dev (Without Skill) | Skill Lift (Delta) |
|--------|-------------------------------|----------------------------------|--------------------|
| Pass Rate (% correct) | 70% avg, +/-26% spread (variable) | 12% avg, +/-11% spread (unreliable) | +57pp |
| Time (s / question) | 46.7s avg, +/-28.0s spread (unreliable) | 15.1s avg, +/-5.1s spread (variable) | +31.6s |
| Tokens (context cost) | 134k avg, +/-30k spread (variable) | 20k avg, +/-405 spread (consistent) | +114k |
