<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Phase-1 radar baselines (VIDETEC)

Offline comparison of **classical cluster+track** and **roadside
segment-then-instance** against RadarPillars on real VIDETEC-2 frames.
DLStreamer / OpenVINO integration is intentionally out of scope here.

## Methods

| Tag | Implementation |
| --- | --- |
| classical | GST `g3dinference` cluster+track; person for \|doppler\| ∈ [0.5, 2.8) m/s **and** compact cluster (extent ≤1.5 m); else vehicle. Score vs **GNSS VRU GT**, not camera. |
| roadside | Compact PointNet semantic seg + class-aware cluster (keeps 1-point objects); GNSS weak labels |
| radarpillars | Prior P0 FT2 / OV-FT2 JSON under `VIDETEC-2/` (not re-run by the harness) |

## Run

```bash
# Needs: VIDETEC-2/.venv (numpy, pyproj) + RadarPillar/.venv (torch) for roadside
python3 sample_data/radar_intersection/baselines/run_phase1_compare.py \
  --epochs 40 --device cuda
```

Outputs land in `VIDETEC-2/phase1_baselines/` (`PHASE1_COMPARE.md`,
`phase1_summary.json`, detection JSONL, roadside checkpoint).

Re-eval only (reuse checkpoint):

```bash
python3 sample_data/radar_intersection/baselines/run_phase1_compare.py --skip-train
```

## Attribution

VIDETEC-2, Zenodo [17799385](https://zenodo.org/records/17799385), CC BY 4.0.
Roadside architecture inspired by Bhanderi et al., Sci. Rep. 2025
([roadside-radar-seg](https://github.com/bhanderisavan/roadside-radar-seg));
**weights are VIDETEC-only** (CC BY 4.0) — see [PROVENANCE.md](PROVENANCE.md).
No RoadsideRadar / INFRA-3DRC (CC BY-NC-SA) data or weights.
