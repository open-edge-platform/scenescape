# observation_conditioning — Implementation Notes: Dropped and Changed Parts

This document lists everything removed or changed from the original (MVP) Python
implementation while porting the library to C++ (ITEP-98737), and explains why.

**Reference implementation:** commit `5cc7f08a8` (ITEP-98099). To view an original file:

```bash
git show 5cc7f08a8:spatial_performance_primitives/observation_conditioning/amodal_reasoner.py
```

All line numbers below refer to that commit.

**Status:** planned. The changes are applied to the Python implementation before the C++ port,
so both implementations share one reference behavior. The C++ port implements only what
remains. The plan is in
[plan-observation-conditioning-cpp-port.md](../../.github/plans/plan-observation-conditioning-cpp-port.md)
(decision D4).

## Legacy backups

The original versions of the files the cleanup changes are kept next to the sources, so the
legacy behavior can be run and compared at any time:

| File | Changed by |
| --- | --- |
| `python/observation_conditioning/amodal_reasoner.py.backup` | §1, §2, §3, §4 |
| `python/observation_conditioning/intersection_map.py.backup` | §3 |
| `python/observation_conditioning/constants.py.backup` | §1, §3 |

They are byte-identical to the files at `5cc7f08a8` (a test checks the SHA-256). The helper
`tests/oc_corpus/legacy.py` imports them as the separate package
`observation_conditioning_legacy`, so original and current code run side by side:

```python
from oc_corpus.legacy import load_legacy
legacy = load_legacy()               # legacy.AmodalReasoner, legacy.DepthMap
```

The baseline generator (`make baseline-original-in-container`) runs the original MVP from them.
Remove the backups, `legacy.py` and the related tests once the authors' follow-up plan is
settled.

## Guarantee: no change in output

Every item below is either **unreachable** or computes values that **never reach the outputs**
of `AmodalReasoner.generate()` or `DepthMap.cast_np()`.

This is verified by freezing a reference baseline from the original implementation on a
scenario corpus that exercises each branch: floor, occluder, wall, total occlusion, spectrum,
degenerate frame, peeling, and a real GLB scene. After the cleanup, outputs must still match it
exactly:

- `updated_depth` and `updated_var` must be bit-identical, along with the per-object decisions
  (FREE_3D, occluded, walled, total occlusion).
- The only observable differences are a few keys in the opt-in debug `trace` (§5) and the
  default `num_layers` (§4), which does not change results.

---

## 1. Non-naive (backward-projection) occlusion — removed

| What | Original location |
| --- | --- |
| Non-naive branch of `_get_occlusion_depth` (`non_naive`, `origins`, `frame`, `over_prem_probe_points`, `num_pins` parameters and the body) | `amodal_reasoner.py` L191-254 (branch L209-252) |
| `_cosine_similarity` (only caller: the non-naive branch) | L112-116 |
| `_calculate_height_from_depth` (only caller: the non-naive branch) | L118-122 |
| `PLANE_DECISION_NML_WEIGHT` (only reader: the non-naive branch) | `constants.py` L9 |

**Why:** the branch is **unreachable**. `generate()` calls `_get_occlusion_depth` (L415) without
`origins`, `frame` or `over_prem_probe_points`, so the guard at L209 is always false and only
the naive check (algorithm Step 8, *Naive Approach*) runs. The branch also has a latent
divide-by-zero (`nmlzd_height_denom` and `nmlzd_sim_denom` become 0 when the forward and
backward projections agree), so it would have needed fixes before it could be enabled.
Porting unreachable code would add C++ code, tests and coverage obligations with no behavioral
value.

**What remains:** the naive occlusion check, unchanged.

**Open for the authors:** algorithm doc Step 8, *Non-Naive Approach: Backward Projection*, now
describes behavior that is not implemented. Options:

- (a) Wire it into `generate()` (with the divide-by-zero fix) as a validated algorithm change,
  in both Python and C++.
- (b) Keep it documented as Future Work.

## 2. Unused pin-drop ground plane and hit points in wall detection — removed

| What | Original location |
| --- | --- |
| `_get_avg_local_ground_plane` call in `_get_wall_depth` (N × 4 downward ray casts per `generate`) | L281-282 |
| Ground-plane signed distances `n_g`, `s_pc`, `s_pt` and the `ground` mask | L297-300 |
| Commented-out height-ordering and `backing` / `naive_wall` logic | L293-295, L302-305 |
| `cand_points`, `lo_vert_points`, `top_points` (camera-ray hit points) | L275-277 |
| `occluded_mask` (read only by the commented-out `backing` line) | L284-286 |
| Unused local `z` | L288 |
| Unused parameters `depth_lo`, `depth_hi`, `occlusion_depth`, `height_eps` of `_get_wall_depth` | L256-260 |
| `_get_avg_local_ground_plane` itself (no callers left after §1 and §2) | L89-110 |

**Why:** the pin-dropped ground plane is computed on every `generate()` call. These are the only
real ray casts in `generate()`; everything else is depth-map lookups. Its only consumer is
`ground`, which is never read, because the `backing` rule that would use it is commented out.
The code comments say it produced false wall positives on bumpy ground. The hit points and
`occluded_mask` feed only that same dead logic or the debug trace. Removing them saves
N × 4 ray casts per frame in Python and avoids porting dead geometry to C++.

**What remains:** the wall decision exactly as executed:

- the signed-angle vertical test on the centroid hit, in the band [75°, 115°);
- otherwise the centroid → top ray spectrum (vertical hits or rising supports);
- the total-occlusion override in `generate()`.

**Open for the authors:** the TODOs at L301-306 propose an OLS best-fit ground plane, with the
gradient magnitude used to tell noise from a real backing surface (algorithm doc Future Work
§1, §2, §4). If that is pursued, the pin-drop helper would come back as part of the new design,
in both Python and C++.

## 3. Constants — consolidated

**Why:** `constants.py` was effectively unused at runtime. Its only imported name,
`PLANE_DECISION_NML_WEIGHT`, is read only by unreachable code (§1). Meanwhile the tuning values
actually in effect were inline literals and default arguments, some of which disagree with the
constants file (`SPECTRUM_SAMPLES = 5` vs. the effective 8 spectrum rays). A port needs a single
source of truth that maps 1:1 to C++ `constexpr` values and that the parity tests can share.

**Change:** `constants.py` holds every value in effect, **with the value currently used at
runtime**. Call sites read from it. No value changes.

| Effective value | Used in (original) | Constant (old name, if any) |
| --- | --- | --- |
| 2.0 σ at-premise probe offset | `_create_probe_points` default `devs`, L57 | new |
| 2.1 σ over-premise probe offset | `generate`, L406 | new |
| 0.1 occlusion threshold, as a fraction of σ_d | `_get_occlusion_depth` `eps`, L200 | `OCC_SIGMA_FRAC` |
| 75° / 115° signed vertical band | `_get_wall_depth` `l_v`, `u_v`, L260 | `VERT_BAND_LOW_DEG` / `VERT_BAND_HIGH_DEG` |
| 75° unsigned vertical threshold (spectrum) | `_wall_spectrum` `l_v`, L148 and L307 | `VERT_BAND_LOW_DEG` |
| 8 spectrum rays | `_wall_spectrum` `num_rays`, L148 | `SPECTRUM_SAMPLES` (was 5, never read) → 8 |
| 0.1 m minimum rise for a rising support | `_wall_spectrum`, L178 (inline) | new |
| 9 column rays, 0.9 blocked fraction, 0.1 m blocker margin | `_total_occlusion`, L319 | new |
| k = 2.0 inflation damping, r_occ = 0.0, 0.1 m wall-vs-occluder margin | `_update_depth_gaussian`, L345-347 | `ADAPTIVE_DAMPING_K` |
| 1e-6 degenerate cross-product tolerance | `_build_orthonorm_frame` L40, `_signed_wall_angle` L141 | new |
| 1e-4 m peel nudge | `DepthMap._peel_rays` `eps`, intersection_map L113 | `PEEL_EPS` |

**Removed, because nothing reads them:**

- `PRIORS` (per-class shape priors; the service resolves priors from Manager assets, and
  `frustum_gaussian` owns the projection prior)
- `MESH_DEFAULT_SIGMA` and `MESH_DEFAULT_VARIANCE`
- `FLOOR_NORMAL_COS_TOL` and `FLOOR_CONSISTENCY_RHO`
- `OCC_EPS` (absolute tolerance of the removed non-naive branch)
- `PLANE_DECISION_NML_WEIGHT` (§1)
- `PEEL_LAYERS` (replaced by the `num_layers` default, §4)

**Open for the authors:** the algorithm doc (Future Work §3) asks for principled or learned
replacements for these heuristics. With this change they live in one table to retune.

## 4. Depth peeling default — 4 → 1 layer

| What | Original location |
| --- | --- |
| `AmodalReasoner.__init__(num_layers=4)` default | `amodal_reasoner.py` L19 |
| Observation Processor `DEFAULT_NUM_LAYERS = 4` | `observation_processor/.../scene_provider.py` L46 |

**Why:** every consumer of the depth map reads **layer 0 only** (`[..., 0]` in
`_get_free_3d_mask`, `generate`, `_get_wall_depth`, `_wall_spectrum`, `_total_occlusion`).
Layer 0 is the same first-hit cast regardless of `num_layers`, so outputs are identical. The
cost of the extra layers is about 2.3× bake time (1080p: 479 ms → 210 ms on a reference mesh)
and 4× depth-map memory (about 530 MB → 130 MB per 4K camera).

**What remains:** peeling is **kept** and ported. `num_layers > 1` still produces
`(H, W, L)` maps, and `DepthMap`'s own default stays 1. Only the defaults change. With the
default of 1, `t_hit_map` has shape `(H, W)`, so the service test that indexes
`t_hit_map[y, x, 0]` is updated.

**Open for the authors:** the constructor comment ("deeper layers the floor") suggests peeled
layers were meant to recover the floor behind an occluder. No step uses them today.

## 5. Debug trace — keys removed

Setting `reasoner.debug = True` fills `reasoner.trace`. These keys disappear with §1 and §2:
`trace["pin_drop"]`, `trace["wall"]["cand_points"]`, `trace["wall"]["ground_point"]` and
`trace["wall"]["ground_normal"]`. All other keys are unchanged. There are no consumers in this
repository. The visualization demos are not vendored here.

## 6. Not ported to C++ (Python only)

These are kept in the Python implementation, but the C++ library does not implement them:

- `AmodalReasoner.mesh`: the original tensor mesh, kept as an attribute but never read. The C++
  reasoner keeps only the ray-casting scene.
- `DepthMap.get_scene()`: returns the Open3D scene; it is Open3D-specific and has no callers.
- `DepthMap.dummy_pixel_map`: a float64 `H × W × 3` pixel grid kept after the bake. C++
  generates the rays inline, so nothing is retained.
- 3 × 4 extrinsics: `populate()` accepts them, but `query()` inverts the matrix and fails for
  3 × 4. C++ takes a 4 × 4 camera→world pose, as `frustum_gaussian` does.

## 7. Found while building the baseline: unreachable empty-interval fallback — kept

`_update_depth_gaussian` falls back to the midpoint of the two bounds when `a >= b` (L376-379
`empty`). Through `generate()` this can never happen: the occluder-face rule drops a wall that
lies within 0.1 m of (or in front of) the occluder, so a remaining wall is always farther than
the occluder (`a < b`). The scenario corpus raises every other decision flag; `EMPTY_INTERVAL`
is the only one it cannot, and the baseline records it as unreachable
(`unreachable_flags` in `tests/data/mvp-original.ocb`).

**Decision:** unlike §1 and §2, this is a cheap defensive branch in the update step itself, so
the C++ port keeps it and tests it directly at the unit level (`detail::update`), not through
the corpus. **Open for the authors:** keep it as a guard, or remove it together with the
midpoint heuristic.

## Not changed (deliberately)

The behavior issues found during analysis are **ported as-is** and left for the follow-up plan:

- nearest-pixel lookups with half-to-even rounding;
- winding-dependent signed wall angle;
- NaN/inf used as sentinels;
- no input validation;
- downward-camera assumption;
- mixed float32/float64 precision.

This keeps the port a pure re-implementation that numerical parity tests can check.
