<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Port `observation_conditioning` to C++ (ITEP-98737)

- **Author(s)**: Tomasz Dorau
- **Date**: 2026-11-26
- **Status**: Phase 4 in progress (WP 4.0 done)
- **Epic**: ITEP-98710 — probabilistic tracking ([plan](plan-probabilistic-tracking.md), [ADR-0019](../../docs/adr/0019-probabilistic-tracking-association.md), [design](../../docs/design/probabilistic-tracking-association.md))
- **Service context**: [Observation Processor design](../../docs/design/observation-processor-service.md)
- **Design (C++)**: [docs/design/observation-conditioning-cpp.md](../../docs/design/observation-conditioning-cpp.md)

## Phases

Each phase ends with a review checkpoint.

1. [x] **MVP analysis**: features, limitations, issues, test coverage, dependencies → [MVP](#mvp)
2. [x] **Porting challenges**: Python dependencies with no C++ equivalent, test gaps, parity risks → [Porting challenges](#porting-challenges)
3. [x] **Design and plan**: C++ design that meets the acceptance criteria and scales on HW → [Porting plan](#porting-plan) + design doc
4. [ ] **Implementation** (in progress): C++ library, Python bindings, unit, regression and parity tests, reference baselines
5. [ ] **Evaluation**: parity and performance against the Python MVP → [Evaluation](#evaluation)

### Acceptance criteria (ITEP-98737)

- C++ rewrite that the Tracker or any other pure-C++ service can link directly.
- C++ interface and structs aligned with `frustum_gaussian`; C++20 minimum.
- Python bindings that drop into the current Observation Processor in place of the MVP.
- Python and C++ unit and functional tests covering about 90% of usages, including failures and corner cases.
- Tests that show Python and C++ produce the same output and behavior.
- A service harness test that shows both implementations give numerically aligned results.
- Performance tests, measured against the Python MVP.

---

## MVP

### Terminology

| Term | Meaning |
| --- | --- |
| **Camera and scene** | |
| K | 3×3 pinhole intrinsics `[[fx,0,cx],[0,fy,cy],[0,0,1]]`. A 3×4 form with a trailing zero column is also accepted. |
| pose, `pose_mat`, extrinsics | 4×4 **camera→world** transform `[R \| t]`. `t` is the camera origin in world coordinates. |
| W×H | Image width × height in pixels. It is also the depth-map resolution. |
| world-up, `rwc_z_up` | Unit world-up vector. The service uses `(0, 0, 1)`. |
| world frame | The scene/mesh coordinate frame. All library inputs and outputs are expressed in it. |
| mesh | Static world-frame triangle mesh of the scene. It excludes the tracked objects. GLB is the file format the service loads it from. |
| **Observations** | |
| N | Number of observations (detections) in one `generate` call. |
| `mu` | In the MVP dict: the **camera origin**, the shared ray origin. In `fg::FrustumObservation` after `transform_to_world`: the **object centroid**. See C4. |
| r, `ray` | Unit world direction from the camera to the object centroid. |
| `depth_est`, `depth_lo`, `depth_hi` | Estimated depth and its near and far bounds along r, from `frustum_gaussian`. Depth here means camera range (distance), not camera-Z. |
| centroid | `mu + r · depth_est`. |
| Σ (`Sigma`) | 3×3 world covariance of an observation. |
| F = [r, e_h, e_v] | Per-object orthonormal frame. e_h is horizontal (r × up). e_v = r × e_h, oriented toward up for probes. |
| Λ = Fᵀ Σ F | Covariance in the ray frame. Its diagonal is (σ_d², σ_h², σ_v²). |
| σ_d, σ_h, σ_v | 1-σ uncertainty along r (depth), e_h and e_v. |
| **Algorithm** | |
| bake | Constructor step: casts one ray per pixel and stores the per-pixel range (`t_hit`) and normal maps. |
| L, `num_layers` | Depth-peeling layers per pixel. Layer 0 is the first hit; deeper layers are the next surfaces along the ray. |
| `t_hit` | Hit distance along a ray. `inf` on a miss. |
| Ng | Geometric (face) normal of the hit triangle, as returned by Embree. |
| probe (at-premise / over-premise) | Points offset from the centroid by ±2σ (at-premise) or ±2.1σ (over-premise) along e_h and e_v. They are looked up in the depth map. |
| FREE_3D | An object with no scene support below it (floating). Its depth passes through unchanged. |
| d_occ, d_wall | Occluder depth (the lower bound) and wall or backing depth (the upper bound) along r. |
| spectrum | Fan of 8 rays from the camera, between the centroid and the top probe. It is used to find walls when the centroid test fails. |
| total occlusion | When ≥ 90% of a 9-target column from the lower probe to the top probe is blocked. |
| δ | Innovation `depth_est − d_occ`. It drives the adaptive variance inflation `max(0, δ² − σ_d²)/k` with k = 2. |
| α, β | Standardized truncation bounds `(d_occ − depth_est)/σ_pre`, `(d_wall − depth_est)/σ_pre`, where σ_pre is σ_d after inflation. They appear as `a`, `b` in the SciPy formulas. |
| pA, pB | Standard-normal truncated PDF evaluated at α and β. |
| empty interval | `d_occ ≥ d_wall`: the bounds conflict, so the midpoint fallback is used. |
| mesh foot | Service feature: ray-cast the bottom-center pixel to the mesh to place the object (`cast_np`). |
| **Software and HW** | |
| MVP | The current Python implementation, the reference for parity. |
| fg | The `frustum_gaussian` library (C++ namespace `fg`). |
| OP | The Observation Processor service. Its modes: AUTO, FULL (frustum + amodal), FRUSTUM_ONLY. |
| Embree | Intel ray-tracing kernels. Open3D's `RaycastingScene` is built on them. |
| BVH | Bounding volume hierarchy, the Embree acceleration structure. |
| `rtcIntersect1` / `rtcIntersect8/16` | Embree single-ray vs. packet ray query. |
| ROBUST | Embree scene flag for watertight, higher-accuracy intersection. |
| TBB | Intel oneTBB task-parallel library. |
| ISA | CPU instruction set (SSE4.2, AVX2, AVX-512). |
| ULP | Unit in the last place, the floating-point rounding granularity. |
| SoA | Structure-of-arrays memory layout. |
| GIL | Python global interpreter lock. |
| I*n*, C*n*, D*n* | Issue, porting-challenge and decision IDs in this document. |

### What it is

[`spatial_performance_primitives/observation_conditioning`](../../spatial_performance_primitives/observation_conditioning/) is about 780 LOC of Python, vendored from `scenescape-v2-architecture`. Given world-frame frustum Gaussians and a static scene mesh, it conditions each object's **scalar depth along its ray** (mean and variance) on floor contact, occlusion and walls.

| Component | File | Role |
| --- | --- | --- |
| `DepthMap` | [intersection_map.py](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/intersection_map.py) | Bakes a per-pixel camera-range and normal map (optionally depth-peeled) with Open3D `RaycastingScene`. `query()` projects world points to the nearest pixel and does an O(1) lookup. `cast_np()` casts arbitrary rays. |
| `AmodalReasoner` | [amodal_reasoner.py](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/amodal_reasoner.py) | One instance per (mesh, K, pose, W×H); the bake runs in `__init__`. `generate(gaus_rays) → (depth, var)`, each of shape `(N,)`. |
| Constants | [constants.py](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/constants.py) | `PLANE_DECISION_NML_WEIGHT` (used), plus tuning constants that are never imported (see issues). |

### Effective pipeline (`generate`, as executed today)

1. Build the frame F = `[r, e_h, e_v]` from the ray and world-up, with a fallback when `r ∥ up` ([L33-46](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/amodal_reasoner.py#L33-L46)). Compute `Λ = Fᵀ Σ F`.
2. Create 5 probe points per object (±2σ horizontal, ±2σ vertical with `e_v` oriented up, and the centroid), plus an "over-premise" copy at 2.1σ. Look both sets up with `DepthMap.query` (no ray casts).
3. FREE_3D: the lower probe misses or lies beyond `depth_hi` at both 2σ and 2.1σ.
4. Occlusion: only the **naive** check runs (lower-probe range vs `depth_est`, and 2σ vs 2.1σ jump > 0.1σ_d).
5. Wall: the signed angle of the centroid-hit normal is in [75°, 115°); otherwise an 8-ray centroid→top "spectrum" looks for vertical hits or rising supports (> 0.1 m).
6. Total occlusion: a 9-target column from the lower probe to the top probe. If ≥ 90% is blocked, drop the occluder and use the nearest blocker as a wall.
7. Update: adaptive inflation `max(0, δ² − σ²)/2`, then truncated-normal moments on `[d_occ, d_wall]` (`scipy.stats.truncnorm.stats`). An empty interval falls back to the midpoint with the inflated variance. FREE_3D or unbounded objects pass through unchanged.

### Service integration (contract for drop-in)

- [scene_provider.py:672-720](../../observation_processor/src/observation_processor/scene_provider.py#L672-L720) builds and caches one `AmodalReasoner(mesh=o3d.t TriangleMesh, rwc_z_up=(0,0,1), K 3×3, pose_mat, W, H, num_layers=4)` per (scene, camera). Cache invalidation uses `id(mesh)`. The bake limit is 3840×2160 px.
- [conditioning.py:158-185](../../observation_processor/src/observation_processor/conditioning.py#L158-L185) calls `reasoner.generate(rays)` with float32 frustum arrays and `mu` overwritten to the camera origin.
- [conditioning.py:188-207](../../observation_processor/src/observation_processor/conditioning.py#L188-L207) also calls **`reasoner.depth_map.cast_np(rays, origin)`** for mesh-foot placement. A drop-in therefore has to expose `depth_map.cast_np` as well as `generate`.
- GLB loading uses `o3d.io.read_triangle_mesh` and stays in the service (outside the library).
- The gRPC server has 4 worker threads, and reasoners are shared across requests.

### Dependencies

| Dependency | Used for |
| --- | --- |
| `open3d` 0.19 (`open3d-cpu`) | `RaycastingScene` (Embree-backed BVH ray casting) and the tensor mesh type |
| `scipy` 1.17 | `truncnorm.stats` (truncated-normal mean and variance) |
| `numpy` 2.2 | Everything else (vectorized, float64 with float32 casts at the ray-casting boundary) |

### Test coverage

| Suite | What it covers |
| --- | --- |
| [tests/test_depth_map.py](../../spatial_performance_primitives/observation_conditioning/tests/test_depth_map.py) (3 tests) | `DepthMap` hit, miss and behind-camera; 2-layer peeling; FREE_3D passthrough |
| [tests/sscape_tests/observation_processor](../../tests/sscape_tests/observation_processor/) | Service paths. `generate` is **mocked** in the numeric tests; the real reasoner runs only on a flat-floor fixture. |

Measured with `pytest --cov --cov-branch`, library tests only: `amodal_reasoner.py` 77% (lines covered only incidentally by the single passthrough test), `intersection_map.py` 90%.

**No test asserts numeric outputs** for occlusion, wall, spectrum, total occlusion, truncation, the empty-interval case, or degenerate frames. There are no reference or golden outputs and no performance tests.

### Baseline performance (indicative)

Measured on an Intel Core Ultra 9 288V (8C, no AVX-512) with the service-pinned wheels, on a floor + wall mesh (24 triangles):

| Operation | 1280×720, L=1 | 1920×1080, L=1 | 1920×1080, L=4 (service default) |
| --- | --- | --- | --- |
| Bake (constructor) | 90 ms | 210 ms | 479 ms |
| `generate` N=1 / 16 / 64 / 256 | 0.69 / 1.45 / 3.19 / 9.97 ms | 0.70 / 1.38 / 3.11 / 10.06 ms | 0.70 / 1.43 / 3.13 / 10.16 ms |

`generate` cost is dominated by numpy and scipy per-call overhead, not geometry: a fixed floor of about 0.7 ms, then about 37 µs per object. The bake scales with pixels × layers and with mesh complexity; it still needs to be measured on real GLB scenes.

### Limitations and issues found

| # | Issue | Where | Impact |
| --- | --- | --- | --- |
| I1 | The non-naive (back-projection) occlusion path is **dead**: `generate` never passes `origins/frame/over_prem_probe_points`. | [L415](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/amodal_reasoner.py#L415) vs [L209](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/amodal_reasoner.py#L209) | Algorithm Step 8 (non-naive) is documented but never runs. It would divide by zero (`nmlzd_*_denom`) if enabled. |
| I2 | The pin-drop ground plane in `_get_wall_depth` is computed (N×4 ray casts) but its result (`ground`) is never used. `cand_points` and `lo_vert_points` are also unused. | [L281-300](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/amodal_reasoner.py#L281-L300) | The only real ray casts in `generate` are wasted work. |
| I3 | Depth peeling (`num_layers>1`) is baked, but every consumer reads layer 0 only. The service default is 4 layers. | `[..., 0]` everywhere; [scene_provider.py:46](../../observation_processor/src/observation_processor/scene_provider.py#L46) | About 2.3× bake time and 4× map memory for no effect. At 4K × 4 layers that is about 530 MB per camera (float32 range + normals), plus a float64 pixel grid kept alive. |
| I4 | `query` uses nearest-pixel `np.round` (half-to-even) with no interpolation. Its in-front test relies on K row 3 = `[0,0,1]`. | [L196-199](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/intersection_map.py#L196-L199) | C++ parity must reproduce half-to-even rounding. Lookups are aliased at grazing angles. |
| I5 | Wall classification uses the **signed** normal angle, so it depends on triangle winding. The spectrum uses the unsigned angle. | [L133-145, L170](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/amodal_reasoner.py#L133-L145) | Meshes with inconsistent winding are classified inconsistently. |
| I6 | The logic depends on NaN/inf semantics (`fmin`, comparisons with NaN evaluate false, inf sentinels) and emits `RuntimeWarning`s. | throughout | C++ must preserve IEEE semantics (no `-ffast-math`). |
| I7 | Most of `constants.py` is unused (`PRIORS`, `MESH_DEFAULT_*`, `PEEL_*`, `OCC_*`, `VERT_*`, `SPECTRUM_SAMPLES=5` vs the inline 8, `ADAPTIVE_DAMPING_K`), and the tunables are duplicated as literals. | [constants.py](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/constants.py) | Unclear source of truth for tuning. |
| I8 | No input validation (shapes, finiteness, `mu == camera origin`, unit rays). The service checks outputs only. | `generate` | Garbage in, silent garbage out. |
| I9 | `debug`/`trace` is mutable instance state on an object shared across gRPC threads. | `self.trace[...]` | Not thread-safe when debug is enabled. |
| I10 | Mixed precision: float32 inputs and ray casting, float64 math. | `cast_np`, `query` | Sets the floor for the C++ parity tolerance. |
| I11 | Documented assumptions: downward-looking cameras, static mesh, the mesh excludes tracked objects, heuristic constants. | [algorithm Future Work](../../spatial_performance_primitives/observation_conditioning/amodal_reasoner_algorithm.md#future-work) | Algorithmic scope, unchanged by the port. |
| I12 | The README requires Python ≥ 3.12, but the service image runs Python 3.11. | README vs [Dockerfile](../../observation_processor/Dockerfile) | Documentation drift. |

---

## Porting challenges

### Decisions recorded

| ID | Decision |
| --- | --- |
| D1 | **Parity target = effective MVP behavior.** Port what `generate` actually computes, quirks included (I3–I5). Skip dead or unused computation that does not affect outputs (I1 non-naive occlusion, I2 unused pin-drop, unused hit points). Behavior fixes (I4–I6, I8, I9) go to a follow-up ticket. |
| D2 | **Mesh input is format-agnostic (option A).** The core takes world-frame `float` vertices and `uint32` triangle indices. GLB loading stays with the caller; the service keeps Open3D for it. A C++ GLB loader module (cgltf, behind an opt-in build flag, with parity tests against Open3D and a fuzz target) is a follow-up (option B), for when in-process Tracker integration is scheduled. |
| D3 | **Service harness** = an in-process gRPC Observation Processor test, run with the Python and C++ backends, comparing responses numerically. |
| D4 | **Pre-port cleanup of the MVP, with no output change.** Remove I1 (dead non-naive occlusion) and I2 (unused pin-drop and hit points). Consolidate I7 (constants keep their effective values). For I3, change the `num_layers` default from 4 to 1 in the service and `AmodalReasoner`; peeling itself is kept and ported. A baseline from the original MVP is frozen first, and the cleaned MVP must match it exactly. Done as separate commits at the start of Phase 4. Details and open points for the original authors are in [implementation.md](../../spatial_performance_primitives/observation_conditioning/implementation.md). The authors may follow up by integrating or extending some of the removed parts. |
| D5 | **Embree is built from source:** the pinned 4.3.3 tarball, static, internal tasking, hidden symbols (design §5.7). Conan `embree` is rejected because it brings a second TBB. |
| D6 | **CI:** add a path-filtered workflow for the C++ build, gtest, coverage gates, Python parity and the service harness (WP 4.9). |
| D7 | **HW evaluation** covers a Xeon (AVX-512) host in addition to the local Core Ultra 9 288V (AVX2). |
| D8 | **Threading runtime: oneTBB** in `oc`, the same as `fg`. The Tracker and robot_vision migrate from OpenMP to oneTBB in follow-ups, so there is one runtime per process (and stronger Intel HW stickiness: `task_arena` core-type and NUMA constraints, OpenVINO alignment). **Required order:** (1) migrate the Tracker; (2) migrate robot_vision, ideally after the Controller is deprecated (planned for 2027.0), which avoids Controller image and Open3D TBB-clash work; (3) only then integrate `oc`/`fg` into the Tracker in-process. A mixed TBB + OpenMP Tracker process never ships. See design §8. |

### C1. Python dependencies without a direct C++ counterpart

| Dependency | What the MVP relies on | C++ counterpart and risk |
| --- | --- | --- |
| `open3d.t.geometry.RaycastingScene` | Open3D 0.19 bundles **Embree 4.3.3** (AVX and AVX2 ISAs, internal tasking) with the `RTC_SCENE_FLAG_ROBUST` flag, the default build quality, a lazy commit, one `rtcIntersect1` per ray with `tnear=0`, `tfar=inf` and TBB grain 1024. `primitive_normals` is the normalized `Ng`. On a miss, `t_hit=inf` and **normals = 0** (the `_peel_rays` layer turns misses into NaN; `cast_np` does not). Verified against the [Open3D v0.19.0 source](https://github.com/isl-org/Open3D/blob/v0.19.0/cpp/open3d/t/geometry/RaycastingScene.cpp). | **Use Embree 4 directly**, pinned to 4.3.3 with the same scene flags, ray setup and miss conventions. That makes bit-identical `t_hit` and normals achievable when both run the same ISA path. Open3D C++ is rejected: it is a heavy dependency for one class. A custom BVH is rejected because of parity risk at triangle edges. |
| `scipy.stats.truncnorm.stats(moments="mv")` | SciPy computes the bound PDFs in log space (`_log_gauss_mass` with `log_ndtr`, a left-tail symmetry trick and `log1p` for the central case). It uses mean = `pA − pB` and the stable variance form `1 + (a−μ)pA − (b−μ)pB`, guards `±inf` bounds via `apply_where`, and loops per object with `np.vectorize`. | Neither the C++ std library nor Eigen has truncated-normal moments or `log_ndtr`. The naive closed form underflows to NaN in the tails: β ≪ 0 happens when a total-occlusion blocker sits far in front of `depth_est` with a small σ. Occluder-only bounds are safe, because the adaptive inflation caps α < √2. **Plan:** port SciPy's algorithm (`log_ndtr` with an asymptotic series for x < −20, plus `log_diff`, `log1p`). Validate it against SciPy on a dense (α, β) grid that includes ±inf, extreme tails and the empty interval. |
| `numpy` | Vectorized float64 math with a float32 boundary at ray casting; `np.round` (half-to-even), `np.linspace`, `fmin`/NaN semantics, `arccos`/`arctan2`/`degrees`. | Reproduce operation order and precision: double for per-object math, float for rays and maps. Use `std::nearbyint` (round-to-nearest-even) instead of `std::round`, an exact `linspace` formula with the endpoint forced to `stop`, and `std::fmin`. Build with `-fno-fast-math`, and explicitly `-ffp-contract=off`, so FMA does not change rounding against numpy. libm and numpy transcendental functions can differ by about 1 ULP, so exact equality is not guaranteed. |

### C2. Numerical parity

- **Discrete decisions amplify ULP noise.** A pixel-rounding tie, the `≥ 75°` angle band, the `> 0.1 m` rising support, `frac ≥ 0.9` (effectively 9 of 9 blocked), and `a ≥ b` can flip on a 1-ULP difference, changing the output by meters. Comparing outputs alone cannot tell a bug from a tie-break.
  - **Mitigation:** C++ emits an optional per-object **decision trace** (free3d, occluded, walled, spectrum, total-occlusion and empty-interval flags, plus bound depths), comparable with the MVP `trace`.
  - Parity tests assert identical decisions plus a tight tolerance on continuous outputs. Any decision flip must be explained by a near-threshold margin, which the test checks explicitly.
- **Mixed precision.** Inputs are float32, the MVP promotes them to float64, and casts back to float32 before ray casting. C++ must cast at the same points. The expected tolerance is about 1e-6 relative on depth and variance when decisions match; Phase 4 will confirm it.
- **ISA dependence.** Embree may choose AVX-512 on Xeon, while Open3D's build caps at AVX2. Edge-hit and ULP results can then differ by host.
  - **Mitigation:** parity tests use meshes and observations away from triangle edges, plus a configurable max-ISA for the Embree device (`isa=avx2`) in parity mode.
- **NaN/inf as control flow** (I6). Port the masks explicitly: `std::isfinite` and `std::isnan` checks in the same places as numpy. Do not rely on comparison side effects.

### C3. Drop-in Python API (Observation Processor)

The service and its tests touch more than `generate`:

| Usage | Location | Requirement |
| --- | --- | --- |
| `AmodalReasoner(mesh=o3d.t TriangleMesh, rwc_z_up, K 3×3/3×4, pose 4×4, W, H, num_layers)` | [scene_provider.py:701](../../observation_processor/src/observation_processor/scene_provider.py#L701) | A thin Python wrapper extracts `mesh.vertex.positions` and `mesh.triangle.indices` as numpy. The native module must not depend on Open3D. Peeling (`num_layers > 1`) must still be implemented, per D1. |
| `reasoner.generate(dict)` → `(depth, var)` float64 | [conditioning.py:177](../../observation_processor/src/observation_processor/conditioning.py#L177) | Same keys, the per-row `mu` origin semantics, output dtypes and shapes. |
| `reasoner.depth_map.cast_np(rays, origin)` → `(normals, t_hit)` | [conditioning.py:201](../../observation_processor/src/observation_processor/conditioning.py#L201) | Same return order; normals are 0 on a miss. |
| `reasoner.depth_map.t_hit_map[y, x, layer]` | [test_cache_warmup.py:543](../../tests/sscape_tests/observation_processor/test_cache_warmup.py#L543) | The map is exposed as a numpy array with the MVP shape rules: `(H,W)` when L=1, `(H,W,L)` otherwise. Expose it as a zero-copy view. |
| `patch.object(reasoner, "generate", ...)` | [test_project_detections.py:130](../../tests/sscape_tests/observation_processor/test_project_detections.py#L130) | Instance attributes must be assignable. Pybind11 classes refuse this, so the public class stays a Python wrapper around the native object. |
| Lazy import with no Open3D at package import (AGENTS invariant 8) | [`__init__.py`](https://github.com/open-edge-platform/scenescape/blob/5cc7f08a82017511d9cd7394dc1a273d4b506adf/spatial_performance_primitives/observation_conditioning/__init__.py) | Keep the lazy `__getattr__`. Backend selection is native-first with fallback to the MVP, following the `frustum_gaussian` pattern, plus an explicit backend override for parity tests. |
| Shared reasoner across 4 gRPC worker threads | [server.py:64](../../observation_processor/src/observation_processor/server.py#L64) | The native `generate` releases the GIL and is re-entrant. The decision trace is per call, not instance state (I9 avoided by construction). |

The service image still needs `open3d` for GLB loading (D2), so the port does not shrink the image yet. Only `scipy` could go, once the MVP fallback is no longer imported in production.

### C4. C++ interface alignment with `frustum_gaussian`

- `fg` uses namespace `fg`, POD structs, float32 C arrays, row-major matrices, pointer + count batch APIs with caller-allocated output, `noexcept`, and TBB `parallel_for` above a threshold.
- **Semantic mismatch:** after `transform_to_world`, `fg::FrustumObservation::mu` is the **object centroid**, while the MVP's `"mu"` is the **camera origin**. The service overwrites it ([conditioning.py:176](../../observation_processor/src/observation_processor/conditioning.py#L176)). The C++ API must not reuse the name with the other meaning.
  - **Direction:** take `const fg::FrustumObservation*` (world frame) and use the reasoner's bound camera origin. Only `ray`, `depth_est/lo/hi` and `Sigma` are read. The Python binding maps the dict with its per-row `mu` origin for parity.
  - **Open (Phase 3):** whether to depend on `frustum_gaussian` headers (types only) or mirror the struct.
- **Error model:** `fg` is `noexcept` and never fails. Conditioning has construction failures (empty mesh, bad K or pose, oversize map, Embree device errors) and input contract violations, so it needs a non-throwing status result on the hot path and exceptions in bindings. `std::expected` is C++23, so with the C++20 floor Phase 3 picks a C++20-compatible result type.

### C5. Build, packaging and toolchain

- **Embree 4 is not in the service base.** `intel/scenescape-common-base` is Debian 12 (bookworm), which ships only **Embree 3.13.5**. Embree 3 has a different API and is not Open3D's version. Debian 13 (trixie) has 4.3.3, and the Tracker image is trixie with conan. Conan Center has `embree/4.3.3`.
  - **Direction:** use conan `embree/4.3.3` for builds and tests (as `fg` already does for gtest), linked statically into the wheel or bundled next to it, like `frustum_gaussian_core`. Keep the ISAs at SSE4.2 + AVX2 (+ AVX-512 optional) with runtime dispatch, so containers stay portable (`-march=native` off).
- **Compiler floor.** The common-base builder uses GCC 12.2 (C++20 is fine; no `<format>`). The local dev machine has GCC 13.3. CI must build with GCC 12.
- **The service image runs Python 3.11**, while the README states ≥ 3.12 (I12). The wheel must be built for the image's interpreter, as `frustum_gaussian` is via `make build PYTHON=/opt/venv/bin/python`.
- **Bundle size.** Embree's static libs add a few MB to the wheel. Shared TBB (`libtbb12`) is already in the runtime image for `fg`.

### C6. Test coverage gaps to close before or with the port

1. **No numeric oracle.** There are no golden outputs for occlusion, wall, spectrum, total occlusion, truncation, or the empty interval. Coverage is 77%, mostly incidental through one passthrough test. Reference baselines must be generated **from the MVP before any C++ exists**, so the oracle is not influenced by the port.
2. **Scenario corpus needed.** The MVP needs deterministic synthetic meshes that trigger each branch:
   - floor only (FREE_3D vs. on-floor)
   - occluder box in front of the object
   - wall behind it
   - wall face coinciding with the occluder (eps rule)
   - a fully occluded column (total occlusion)
   - a slope with rising supports (spectrum)
   - a ray parallel to world-up (degenerate frame)
   - a 3×4 K
   - a point behind the camera, out of frame, or a miss
   - peeled layers
   - inconsistent winding (I5)

   Add one real GLB (the rolling-terrain dataset). Observations are random but seeded, plus hand-placed edge cases near thresholds.
3. **Failure-path tests.** C++ and bindings need tests for empty mesh, non-finite inputs, wrong shapes, zero-size image, oversize map, and N=0. The MVP has undefined behavior for many of these, so the C++ contract (fail vs. pass through) must be defined in Phase 3 without changing results on valid input (D1).
4. **Parity matrix.** The same corpus runs through pure Python (MVP), the native module via Python, and C++ gtest against stored baselines (`.npz` → a small binary or JSON fixture readable by C++).
5. **Service harness (D3).** Today the service tests mock `generate`. The new test runs the in-process gRPC server on a real mesh, in FULL and FRUSTUM_ONLY with `project_to_map`, once per backend, and compares responses field by field.
6. **Coverage tooling.** Use gcovr (line ≥ 90%, the same gate as `fg`'s `CPP_COVERAGE_LINE_MIN`) and `pytest-cov` for the Python wrapper and fallback.
7. **Performance tests.** None exist. Add Google Benchmark (already installed; `fg` has a `FG_BUILD_BENCHMARKS` hook) and a pytest benchmark comparing backends at fixed scene sizes. That covers bake vs. resolution × layers × mesh size, and `generate` vs. N.

### C7. Performance and HW scaling

- **Bake** (the constructor) dominates: 210 ms at 1080p with L=1 and 479 ms with L=4 on a toy mesh. It is already Embree under the hood, so gains come from fusing pixel→ray generation (no float64 H×W×3 temporaries), packet tracing (`rtcIntersect8/16` over coherent pixel tiles, where Open3D uses `rtcIntersect1`), and TBB tiling. Packet results are not guaranteed to be bit-identical to `rtcIntersect1`. Phase 4 verifies this on the corpus, and the bake falls back to `rtcIntersect1` (still tiled and fused) if they differ.
  - Memory: store maps as float32 SoA, with normals optionally compressed; keep the MVP float32 values for parity.
  - The L=4 waste (I3) is removed by the default change in D4, before the port. Phase 5 compares against the cleaned MVP, so C++ gets no credit for it.
- **`generate`** is overhead-bound in Python: a 0.7 ms floor plus about 37 µs per object, partly from `np.vectorize` in truncnorm. In C++ the work per object is about 30 map lookups and a few transcendental functions, so it should be µs-scale.
  - Parallelize over objects with TBB only above a threshold, like `fg`'s 64, because typical N is 1–64.
  - Release the GIL so the 4 gRPC workers can run concurrently.
- **HW variety:** edge CPUs (Atom, Core Ultra; no AVX-512) and Xeon (AVX-512) need runtime ISA dispatch, not compile-time. Also allow a thread-count cap (an Embree device `threads=` setting and a TBB arena) so the library does not oversubscribe when linked into the multi-threaded Tracker.
- **GPU or SYCL Embree** is out of scope; the bake is a one-off and `generate` is too small to benefit. Note it as a future option.
- **Intel HW stickiness and future Intel optimizations.** The baseline stays portable (generic x86-64, runtime dispatch, no `-march=native`). The stack is already Intel's own: Embree and oneTBB. Design hooks so Intel HW gets measurable extras without forking the code:
  - **AVX-512 Embree kernels on Xeon.** Open3D builds without them. They are enabled in our build and selected at runtime.
  - **Intel oneAPI icpx multi-ISA builds** (`-ax`, not `-xHost`; the `fg` CMake already handles IntelLLVM). VTune is used for profiling.
  - **Hybrid P/E-core placement** with oneTBB `task_arena` core-type constraints (needs `tbbbind`), so the per-frame path stays on P-cores when linked into the Tracker.
  - **Future: Embree SYCL bake on Intel Xe or Arc GPUs** (Core Ultra iGPU) for many-camera or 4K warm-up. Batched multi-camera `generate`.

## Porting plan

The design is in [docs/design/observation-conditioning-cpp.md](../../docs/design/observation-conditioning-cpp.md). Work packages run in order. Each ends with all existing suites green, and each lands as its own commit (or commits), after approval.

| WP | Scope | Exit criteria |
| --- | --- | --- |
| **4.0 Test environments and baseline freeze** | Pinned Python venv (`make venv`, OP runtime versions) and the dedicated test container (`Dockerfile.test` on common-base: GCC 12.2, Python 3.11), as in design §5.9. Corpus generator: synthetic scenario meshes as code, plus the rolling-terrain GLB, seeded and threshold-edge observations. `.ocb` writer. Generate `mvp-original.ocb` from the original MVP (`5cc7f08a8`). | The venv and the container build reproducibly. Every corpus scenario reaches its target branch (asserted from the MVP `trace`). Baseline committed, generated in the container (Python 3.11). |
| **4.1 Layout move** | `git mv` to the `fg`-style layout (`python/`, `cpp/`, `tests/`). Update the root `Makefile` (`SPATIAL_PERFORMANCE_*`, `COMPLEXITY_SOURCES`), the OP `Dockerfile`, the OP test `conftest.py` and doc links. | No logic diff. The library and OP unit suites are green. |
| **4.2 MVP cleanup (D4)** | One commit each for I1, I2, I7 and I3 (defaults, plus the `t_hit_map` test update). Add a debug-only decision trace to the reference. Generate `reference.ocb`. Update the README, AGENTS and algorithm doc pointers. | Bit-exact match against `mvp-original.ocb`. implementation.md status set to "applied". |
| **4.3 C++ core: geometry and maps** | CMake, pinned Embree source build, `Device`, `SceneGeometry`, `DepthMap` (bake, peel, query, cast), conan for test dependencies, gtest. | Maps match Open3D within the §5.5 targets (via a temporary pybind smoke module or the C++ reader). Unit tests green. |
| **4.4 Truncated normal** | `detail::truncnorm_mv` plus the SciPy grid fixture generator. | rtol 1e-12 on the grid, including ±inf and the tails. |
| **4.5 C++ core: reasoner** | `AmodalReasoner::condition`, `DecisionTrace`, `constants.hpp`, TBB path, `ExecutionOptions`. Corpus regression in C++. | Decisions identical, values within tolerance against `reference.ocb`. Concurrency test green. |
| **4.6 Python bindings and drop-in** | `bindings.cpp`, `_native.py`, backend selection, `pyproject.toml`. Run the library and OP unit suites with each backend. | Both backends pass every existing test. Parity and fuzz tests green. Python coverage ≥ 90%. |
| **4.7 Service integration and harness** | The OP Dockerfile builds the wheel (Embree build stage). `DEFAULT_NUM_LAYERS = 1`. In-process gRPC harness test with both backends. Log the active backend. | Harness responses aligned (§5.9). The image builds, and `make run_sscape_unit_suite` is green. |
| **4.8 Benchmarks, coverage and docs** | Google Benchmark suite, Python backend comparison script, gcovr and pytest-cov gates in the package `Makefile`, OP design doc §5.2 update, README and AGENTS for the C++ API. | C++ line ≥ 90%, branch ≥ 50%. Benchmarks run locally. |
| **4.9 CI** (D6) | Path-filtered workflow: C++ build, gtest, coverage, Python parity, harness. | Workflow green on the PR. |

**Phase 5 (Evaluation)** reports three things:

- Parity: decision agreement and the max/p99 absolute and relative differences per scenario, map ULP statistics, and harness diffs.
- Performance: bake and `condition`/`generate` (C++ and through Python) against the **cleaned** MVP, plus the harness's per-request latency.
- HW scaling: thread sweep, ISA (Core Ultra AVX2 vs Xeon AVX-512, D7), and traversal mode.

## Evaluation

_Phase 5._
