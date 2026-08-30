<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan B — End-to-end workload characterization

Companion: [Plan A — Track() peak-FPS microbenchmark](./plan-track-microbench-fps.md).

## Goal

Characterize **Scene Controller** under realistic MTMC load using [nvidia/PhysicalAI-SmartSpaces](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces): **quality + performance** across scale vectors, with/without ReID, adaptive to available compute. Compare this branch before/after via **git worktrees**.

ADR: [docs/adr/0009-tracking-evaluation.md](../../docs/adr/0009-tracking-evaluation.md) already lists this dataset as future work.

## Architecture

Extend `tools/tracker/evaluation/`:

- New `datasets/physicalai_smartspaces.py` — HF cache; 2025/2026 JSON GT + `calibration.json`; camera/object subsample; MotChallenge3D GT + canonical MQTT detections.
- Scale-sweep runner over `BlackBoxHarness` (Controller-TC primary; OTEL drop metrics via existing `metrics_recorder`).
- Resource sampler: CPU + memory always; GPU (`nvidia-smi`) / NPU if present, else `n/a`.
- Analytics + REST for ROI/tripwire vectors.

**Feed model:** oracle MQTT detections from GT 2D boxes (isolates controller/analytics/tracker; not DLStreamer). GPU/NPU mainly meaningful with ReID (or a later optional video path).

## Scale vectors

1. Objects (all cams): 10, 50, 100, 300
2. Categories: 10 objects × 1, 5, 10, 30 categories (synthetic labels OK beyond native classes)
3. ROIs: 300 objects × 1, 10, 20, 50 regions
4. Cameras: 300 objects × 1, 5, 10, 30 cameras
5. Tripwires: 300 objects × 1, 10, 20, 50 tripwires

**Adaptive stop:** escalate within a vector; skip higher steps on drop rate > ~0.1%, OOM, or sustained CPU/memory over ceiling.

## Metrics per cell

- Quality: HOTA, AssA, LocA, MOTA, IDF1, IDSW
- Peak sustainable publish/chunk rate under drop budget
- `fell_behind` drops; `tracker_busy` (work queue not empty) drops
- CPU, memory; GPU/NPU when available
- Full matrix × ReID on/off

## Git before/after

Same harness on merge-base vs `prob-tracking` HEAD; report FPS/drops/HOTA deltas (association/branch cost under MTMC load).

## Phased delivery

1. Dataset adapter + smoke (1 scene, few cams, 10 objects) + HOTA
2. Resource sampler + OTEL drops
3. Object-count + camera vectors
4. Category vector
5. ROI + tripwire vectors
6. ReID on/off
7. Git worktree A/B report

## Out of scope (this plan)

- robot_vision Google Benchmark / kernel-only FPS — see Plan A
- Committing HF media into git
- Full DLS video decode on every cell (optional follow-on)

## Status

- **Not started** — dataset adapter and scale harness pending.
