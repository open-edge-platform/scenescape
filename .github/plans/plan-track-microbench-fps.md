<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan A — Track() peak-FPS microbenchmark

Companion: [Plan B — E2E workload characterization](./plan-e2e-workload-characterization.md).

## Goal

Measure **peak sustainable FPS** of the shared tracking kernel (`MultipleObjectTracker::track`) used by Scene Controller — fast, local, no Docker/MQTT.

**Definition:** `peak_fps = 1000 / mean_ms_per_track_call` (one category worker, single-threaded). Time-chunking sustains rate `R` only if mean latency < `1/R`.

## Approach

1. **Generic tool** in `controller/src/robot_vision/benchmarks/`:
   - Workload knobs: `--people` (default 50), `--cameras` (1 and 2-cam cases).
   - Optional `--association-config` JSON (`method`, `gate_probability`, `max_radius_m`); if omitted, use that commit’s default `track()` path.
   - Output: Google Benchmark JSON + derived **peak_fps**.
   - Keep/fix `build_benchmark.sh`, `run_benchmark.sh`, `compare_benchmarks.sh`.

2. **Before/after via git** (not baked into the tool):
   - Worktree at merge-base `5b310ecd` vs `prob-tracking` HEAD.
   - Same CLI/workloads; HEAD passes production association config (`position_mahalanobis`, `max_radius_m: 10`).
   - Backport **only the harness** into the base worktree if needed so workloads match.

3. **Report:** peak FPS delta (%); note microbench ≠ full Controller (no MQTT/Python/ReID).

## Prerequisites

- `cmake`, `libbenchmark-dev`, existing robot_vision OpenCV deps.

## Out of scope (this plan)

- PhysicalAI dataset, ROIs/tripwires, ReID, HW accelerator matrix, HOTA — see Plan B.

## Status

- **Done (2026-08-16):** Generic harness + git A/B microbench results in
  `controller/src/robot_vision/benchmarks/out/COMPARISON.md`.
