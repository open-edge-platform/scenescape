<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: scenescape-setup

**Model**: gpt-5.6-terra
**Date**: 2026-08-06T23:37:15Z
**Evals**: 1, 2, 3, 4, 5 (1 run(s) each per configuration)

## Summary

> **How to read this table** -- **Avg** is the mean score across all evals; **Std Dev** (the +/- spread) measures how much individual evals varied around that average -- small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with - without).

| Metric | Avg +/- Std Dev (With Skill) | Avg +/- Std Dev (Without Skill) | Skill Lift (Delta) |
|--------|-------------------------------|----------------------------------|--------------------|
| Pass Rate (% correct) | 100% avg, +/-0% spread (consistent) | 4% avg, +/-10% spread (unreliable) | +96pp |
| Time (s / question) | 24.7s avg, +/-1.1s spread (consistent) | 11.3s avg, +/-3.6s spread (variable) | +13.4s |
| Tokens (context cost) | 149k avg, +/-21k spread (consistent) | 20k avg, +/-454 spread (consistent) | +128k |
