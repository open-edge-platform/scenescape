# frustum-gaussian — AI Agent Guide

This file provides context for AI coding agents working in this repository.
Read it before making any changes.

---

## What this library is

A **pure projection kernel**: converts N 2D bounding boxes (pixel coordinates) + camera
intrinsics + per-class shape priors into N **ray-elongated 3D Gaussian observations** in
camera or world frame. It is fast, numerically careful, and deliberately narrow in scope.

It does **not**:

- Apply surface / terrain constraints (that is the Phase 2 scene-projection library)
- Decide whether an object is on the ground or flying (Phase 2 concern)
- Track objects across frames (Phase 3)
- Fuse observations from multiple cameras (Phase 3a)

The interface boundary is the `FrustumObservation` struct. Everything downstream of
`transform_to_world_batch()` belongs to another library.

---

## Repository layout

```
include/frustum_gaussian/
    types.hpp        — all public structs (BoundingBox, Intrinsics, ShapePrior,
                       DetectorNoise, FrustumObservation)
    frustum.hpp      — public API declarations
src/
    frustum.cpp      — single-detection kernel: project_frustum(), transform_to_world()
    batch.cpp        — batched kernel: project_frustum_batch(), TBB parallelism
python/              — pybind11 bindings
tests/               — unit + integration tests
benchmarks/
    bench_batch_variants.py   — N=1-100 Python benchmark (NumPy / serial / opt)
    REPORT.md                 — benchmark results and analysis
README.md            — quick-start, math summary, build
ALGORITHM.md         — full algorithm derivation, architecture, deployment scenarios
```

---

## Invariants — never break these

1. **`project_frustum` and `project_frustum_batch` must remain `noexcept`.**
   Callers in real-time pipelines cannot handle exceptions.

2. **Covariance `Sigma` must always be positive semi-definite.**
   The eigendecomposition form `σ_h²·e_h·e_hᵀ + σ_v²·e_v·e_vᵀ + σ_d²·r·rᵀ` guarantees
   this by construction. Do not change to direct matrix arithmetic without proof of PSD.

3. **`PARALLEL_THRESHOLD = 64` — do not lower without re-benchmarking.**
   Validated on Intel Core Ultra X7 368H. Below 64 the TBB thread-wake cost (~2-4 µs)
   dominates the parallel work, making the optimized variant _slower_ than serial.
   See `benchmarks/REPORT.md` for the full N=1-100 dataset.

4. **Use `atan` for angular subtenses — not the small-angle approximation.**
   For FOV > ~50° the small-angle form (α ≈ Δu/f) introduces 3-5% depth error at image
   edges — up to 1.5 m at 30 m on a typical scene camera. The `atan` form is exact.

5. **`CLIP_MARGIN_PX = 3` and `DetectorNoise.sigma_px` are not redundant — do not merge.**
   - `CLIP_MARGIN_PX` is a binary structural gate: is this edge geometrically truncated?
     A clipped edge is excluded from depth estimation and sets `depth_lo = 0`.
   - `sigma_px` is continuous Gaussian noise applied to edges that _are_ present.
   - The margin (3 px) is deliberately larger than the noise (2 px): an edge 2-3 px from
     the image border is almost certainly truncated, not merely noisy.

6. **`sigma = 0` in `ShapePrior` is valid — it activates the auto-prior (`mu × 0.40`).**
   Treat it as "size unknown; use a wide learned prior." Never reject or warn on sigma=0.

7. **Do not re-introduce a detector-resolution ceiling on `depth_hi` (e.g. `min_box_px`).**
   A `DetectorNoise.min_box_px` field was added and then reverted: the observed bounding
   box already encodes resolution implicitly — a detection cannot exist if the object were
   too small or too distant to subtend that box. Mixing a detector engineering heuristic
   into a geometric bound does not improve the bound where depth is reliable.
   Keep `depth_hi = min(dim_hi/(2·tan_x_half), dim_hi/(2·tan_y_half))` solely from
   shape-prior geometry. See ALGORITHM.md §5.5.

---

## Key algorithm steps (for code review / extension)

| Step | File                                      | What it does                                                       |
| ---- | ----------------------------------------- | ------------------------------------------------------------------ |
| 1    | `frustum.cpp` `detect_clipped()`          | Gate edges within 3 px of image boundary                           |
| 2    | `frustum.cpp`                             | Normalize box corners through intrinsics → center ray r̂            |
| 3    | `frustum.cpp`                             | Orientation-agnostic bounds: dim_lo/dim_hi across all 3 prior axes |
| 4    | `frustum.cpp`                             | Angular subtenses via atan (horizontal + vertical)                 |
| 5    | `frustum.cpp` `depth_from_angular_size()` | Depth + uncertainty per unclipped axis                             |
| 6    | `frustum.cpp` `fuse_depths()`             | Information-form (inverse-variance) fusion                         |
| 7    | `frustum.cpp`                             | Compute depth_lo / depth_hi geometric bounds                       |
| 8    | `frustum.cpp`                             | Assemble Σ_cam via eigendecomposition (PSD guaranteed)             |
| 9    | `frustum.cpp`                             | Cauchy quality score: Σ_char²/(Σ_char²+σ_d²), Σ_char=30 m          |
| —    | `batch.cpp`                               | TBB `parallel_for` wrapper with scalar fallback for N < threshold  |

---

## Output struct reference

```cpp
struct FrustumObservation {
    float mu[3];        // position mean in camera frame [x, y, z] (m)
    float Sigma[9];     // 3×3 covariance, row-major (m²) — always PSD
    float ray[3];       // unit center ray (camera frame)
    float depth_est;    // MAP depth along ray (m)
    float depth_sigma;  // 1-σ depth uncertainty (m)
    float depth_lo;     // soft near bound — 0 if any axis is clipped (m)
    float depth_hi;     // soft far bound — valid even when clipped (m)
    float score;        // depth constraint quality ∈ [0, 1]
    uint8_t edge_valid; // bit-mask: LEFT=0x01 RIGHT=0x02 TOP=0x04 BOT=0x08
                        // bit=1 means that edge IS unclipped (valid)
};
```

After `transform_to_world()`: `mu`, `Sigma`, `ray`, and `depth_*` are in world
frame. Depth estimates and bounds follow the transformed ray length;
`depth_sigma` is the standard deviation projected along the normalized world ray.
`score` and `edge_valid` are frame-invariant.

---

## Object modes — Phase 2 decides, not this library

This library returns the same unconstrained Gaussian regardless of object class.
The downstream **scene-projection library** (planned, not yet built) applies:

- **Scene-projected** (vehicles, pedestrians, shelf items, anything touching a surface):
  intersect center ray with terrain mesh → condition Gaussian on terrain z.
- **FREE_3D** (drones, birds, aircraft, retail products being carried, any unknown posture):
  pass raw Gaussian to information-form fuser; depth resolved by multi-camera intersection
  or temporal velocity bounds.

Do not add mode-switching logic to this library. The `edge_valid`, `depth_lo`, `depth_hi`,
and `ray` fields carry all the information the Phase 2 layer needs.

**GRAVITY_ALIGNED** (upright vertical axis) is a learnable per-class property, not an
a priori assumption. Most ground-contact objects do not have a known orientation from a
single bounding box. Surface contact (scene-projected) and vertical alignment are separate
concepts.

---

## Temporal constraints — Phase 3 decides, not this library

- Velocity bounds from world-coordinate displacement across frames
- Size refinement from repeated unoccluded traversals (angular subtense sequence)
- Maximum observed extent overrides class prior in tracker state

These flow back as tightened `ShapePrior` values on the _next_ call to
`project_frustum_batch`. The library itself is stateless.

---

## Typical class priors

| Class          | μ_x  | μ_y  | μ_z    | Phase 2 mode    |
| -------------- | ---- | ---- | ------ | --------------- |
| Pedestrian     | 0.55 | 0.55 | 1.70 m | Scene-projected |
| Cyclist        | 0.65 | 1.10 | 1.60 m | Scene-projected |
| Car            | 2.00 | 4.50 | 1.50 m | Scene-projected |
| Bus            | 2.50 | 9.00 | 3.20 m | Scene-projected |
| Drone          | 0.30 | 0.30 | 0.20 m | FREE_3D         |
| Bird           | 0.40 | 0.25 | 0.15 m | FREE_3D         |
| Aircraft       | 15.0 | 12.0 | 4.0 m  | FREE_3D         |
| Retail product | 0.12 | 0.08 | 0.20 m | FREE_3D         |

Retail products are FREE_3D because they are carried at arbitrary heights. Their wide
σ_z (0.12 m) reflects the enormous variety of product heights within a single class.

---

## Build and test

```bash
# Python wheel (preferred for development)
pip install .
pytest tests/

# C++ with tests
cmake -B build -DCMAKE_BUILD_TYPE=Release -DFG_BUILD_TESTS=ON
cmake --build build -j$(nproc)
ctest --test-dir build --output-on-failure

# Benchmark (N=1-100, 20 000 reps)
python3 benchmarks/bench_batch_variants.py --reps 20000 --warmup 500
```

---

## Common patterns

**Single detection (C++):**

```cpp
fg::Intrinsics K(fx, fy, cx, cy, width, height);
fg::ShapePrior prior(mu_x, mu_y, mu_z, sigma_x, sigma_y, sigma_z);
fg::FrustumObservation obs = fg::project_frustum(bb, K, prior);
fg::FrustumObservation obs_w = fg::transform_to_world(obs, pose_mat); // row-major 4×4
```

**Batch (Python, preferred for real-time):**

```python
result = fg.project_frustum_batch(
    boxes,                                              # (N,4) float32
    intrinsics=np.array([fx, fy, cx, cy], dtype='f4'),
    img_size=np.array([width, height], dtype='f4'),
    priors=priors,                                      # (N,6) float32
)
world = fg.transform_to_world_batch(result, pose_mat)  # pose_mat: (4,4) float32
```

**Clipping override (explicit, not auto-detected):**

```cpp
fg::BoundingBox bb(u0, v0, u1, v1);
bb.clipped = fg::EDGE_LEFT | fg::EDGE_TOP;  // explicit: left and top are clipped
```

---

## Known limitations and open work

- **Scene-projection library (Phase 2):** Not yet built. Surface conditioning, FREE_3D
  passthrough, and upright-axis flag are all planned for this separate optimized component.
- **Mermaid chart colors:** `%%{init}` `plotColorPalette` directives in `xychart-beta`
  are ignored by the GitHub Markdown renderer. Colors render correctly in local Markdown
  previews only. This is a GitHub limitation, not a bug in the charts.
- **Heading-aware depth:** If a per-object heading prior becomes available (e.g. from
  tracker state), it can be passed as a tighter `ShapePrior` to reduce σ_d. The library
  already supports this via `sigma_x/y/z` — no API change needed.
