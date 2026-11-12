# observation_conditioning — AI Agent Guide

This file provides context for AI coding agents working in this package.
Read it before making any changes.

---

## What this library is

Mesh-aware **depth conditioning** for frustum-Gaussian observations. Given
world-frame ray Gaussians from `frustum_gaussian` plus a **static** scene mesh, it
updates per-object depth mean and variance for floor/shelf contact, occlusion, and
walls (`AmodalReasoner.generate`).

It does **not**:

- Project 2D boxes into Gaussians (that is `frustum_gaussian`)
- Associate tracks or fuse multi-camera measurements
- Handle dynamic meshes (depth map is baked once at construction)

One `AmodalReasoner` instance is bound to a single `(mesh, camera K, camera→world
pose, resolution)`. Rebuild if the mesh or camera geometry changes.

---

## Package layout

```
amodal_reasoner.py              — AmodalReasoner pipeline (generate)
intersection_map.py             — DepthMap: dense ray-cast depth/normal bake + query
constants.py                    — PLANE_DECISION_NML_WEIGHT, class PRIORS
__init__.py                     — lazy exports: AmodalReasoner, DepthMap
tests/test_depth_map.py         — unit coverage for DepthMap / generate
README.md                       — quick start
amodal_reasoner_algorithm.md    — full algorithm notes (Steps 0–10, Future Work)
```

Import root is `spatial_performance_primitives/` on `PYTHONPATH`:

```python
from observation_conditioning import AmodalReasoner
```

The Observation Processor image copies this directory to
`/app/observation_conditioning`.

---

## Invariants — never break these

1. **World frame everywhere; `mu` is the camera origin.**
   Rays must emanate from the camera (`mu == extrinsics[:3, 3]` for every row).
   Upstream frustum camera-frame outputs must be transformed to world first.

2. **Tensor mesh required.**
   Pass `o3d.t.geometry.TriangleMesh` (convert legacy with `from_legacy`). The mesh
   must be static and must **not** contain the dynamic objects being tracked.

3. **Extrinsics are camera→world.**
   `DepthMap` / `AmodalReasoner` treat the 4×4 pose as camera-to-world. Do not pass
   world-to-camera without inverting.

4. **Bake once per camera geometry.**
   `DepthMap.populate()` runs in `__init__`. Do not mutate mesh/K/pose on a live
   instance; construct a new reasoner.

5. **`generate` returns scalar depth along `ray`, not a full 3D Gaussian.**
   Callers rebuild centroids as `mu + ray * updated_depth`. Do not change the
   return contract to world XYZ without updating Observation Processor.

6. **FREE_3D and unbound objects pass through.**
   When no scene bound applies, `updated_depth = depth_est` and
   `updated_var = σ_d²` from the input covariance. Do not force surface hits on
   free-flying classes.

7. **Downward-ish cameras are assumed.**
   Floor/occlusion probe logic expects a camera angled toward the scene. Level or
   upward cameras are Future Work — do not silently “fix” them without tests.

8. **Keep open3d imports lazy at package import.**
   `__init__.py` uses `__getattr__` so installing/importing the package name does
   not require open3d until `AmodalReasoner` / `DepthMap` are touched.

---

## Key algorithm steps (for code review / extension)

See `amodal_reasoner_algorithm.md` for math. Code map:

| Step | Where                 | What it does                                           |
| ---- | --------------------- | ------------------------------------------------------ |
| 0    | `intersection_map.py` | Bake per-pixel depth/normal maps via Open3D raycasting |
| 1–2  | `amodal_reasoner.py`  | Orthonormal ray frame; probe offsets from Σ            |
| 5–6  | `amodal_reasoner.py`  | At-premise / over-premise mesh queries                 |
| 7    | `_get_free_3d_mask`   | FREE_3D passthrough decision                           |
| 8    | occlusion path        | Depth discontinuity / plane decision                   |
| 9    | wall / spectrum path  | Nearer-surface-as-wall candidates                      |
| 9.5  | visibility fraction   | Partial vs total occlusion                             |
| 10   | truncnorm update      | Condition depth mean/variance on interval bounds       |

Tunable constants live in `constants.py` and inline in `amodal_reasoner.py`. Prefer
documenting changes in Future Work over silent retunes.

---

## Input / output contract

**Constructor:** mesh, `rwc_z_up` `(3,)`, `K` 3×3 or 3×4, camera→world `4×4`,
`width`, `height`, optional `num_layers` (default 4; use 1 for first-hit only).

**`generate(gaus_rays)` reads:** `mu`, `Sigma`, `ray`, `depth_est`, `depth_lo`,
`depth_hi`. Other frustum fields (`depth_sigma`, `score`, `edge_valid`) may be
present but are not consumed today.

**Returns:** `(updated_depth, updated_var)` each shape `(N,)`.

Set `reasoner.debug = True` before `generate` to fill `reasoner.trace` with
intermediates (tests / debugging only).

---

## Build and test

```bash
# From repo root, with spatial_performance_primitives on PYTHONPATH:
PYTHONPATH="spatial_performance_primitives${PYTHONPATH:+:$PYTHONPATH}" \
  tests/.venv/bin/python -m pytest \
  spatial_performance_primitives/observation_conditioning/tests -q

# Or via the Observation Processor unit suite (also exercises integration):
make run_sscape_unit_suite
```

Dependencies: Python ≥ 3.12, `numpy`, `open3d` (> 0.19), `scipy`, `pytest`.

---

## Common pattern

```python
import numpy as np
import open3d as o3d
from observation_conditioning import AmodalReasoner

mesh = o3d.t.geometry.TriangleMesh.from_legacy(
    o3d.io.read_triangle_mesh("scene.glb"))
reasoner = AmodalReasoner(mesh, z_up, K, extrinsics_c2w, W, H, num_layers=1)
updated_depth, updated_var = reasoner.generate(gaus_rays_world)
```

---

## Known limitations and open work

Documented in `amodal_reasoner_algorithm.md` **Future Work**: robust ground-plane
fit, outlier rejection in pin-dropping, non-downward cameras, dynamic scenes,
replacing heuristic constants, upright-axis refinements.

Attribution for algorithm notes: preserve author credit in
`amodal_reasoner_algorithm.md` (Michael Gadda, Robert A. Watts) when deriving from
that document.
