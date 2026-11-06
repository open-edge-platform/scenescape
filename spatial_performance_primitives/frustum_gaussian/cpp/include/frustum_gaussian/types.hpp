// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <cstdint>

namespace fg {

// ---------------------------------------------------------------------------
// Edge clipping bit flags.
// Bit = 1 means the corresponding bounding-box edge is NOT clipped by the
// image border (i.e. the true object boundary is visible).
// ---------------------------------------------------------------------------
constexpr uint8_t EDGE_LEFT   = 0x01;
constexpr uint8_t EDGE_RIGHT  = 0x02;
constexpr uint8_t EDGE_TOP    = 0x04;
constexpr uint8_t EDGE_BOTTOM = 0x08;
constexpr uint8_t EDGE_ALL    = 0x0F;

// ---------------------------------------------------------------------------
// BoundingBox — axis-aligned bounding box in pixel coordinates.
//
// Coordinate convention:  u increases rightward, v increases downward
// (standard OpenCV / image convention).
//
// clipped:  bit-mask where bit N = 1 means that edge IS clipped by the image
//           boundary (bit layout: LEFT=0x01, RIGHT=0x02, TOP=0x04, BOT=0x08).
//           Use CLIPPED_AUTO (0xFF) to let the library infer clipping from the
//           image dimensions stored in Intrinsics.
// ---------------------------------------------------------------------------
struct BoundingBox {
    float u_min;  ///< left edge (pixels)
    float v_min;  ///< top edge  (pixels, smaller = higher in image)
    float u_max;  ///< right edge (pixels)
    float v_max;  ///< bottom edge (pixels, larger = lower in image)

    /// Explicit clipping override (bit=1 → that edge IS clipped).
    /// Set to CLIPPED_AUTO to infer from image dimensions (± CLIP_MARGIN_PX).
    uint8_t clipped = CLIPPED_AUTO;

    static constexpr uint8_t CLIPPED_AUTO    = 0xFF;
    static constexpr float   CLIP_MARGIN_PX  = 3.0f;

    // convenience ctor for the common auto-detect case
    BoundingBox(float u0, float v0, float u1, float v1) noexcept
        : u_min(u0), v_min(v0), u_max(u1), v_max(v1) {}
    BoundingBox() noexcept = default;
};

// ---------------------------------------------------------------------------
// Intrinsics — pinhole camera model (after lens undistortion).
// ---------------------------------------------------------------------------
struct Intrinsics {
    float fx;      ///< horizontal focal length (pixels)
    float fy;      ///< vertical   focal length (pixels)
    float cx;      ///< principal point x (pixels)
    float cy;      ///< principal point y (pixels)
    float width;   ///< image width  (pixels) — used for auto edge-clip detection
    float height;  ///< image height (pixels)

    Intrinsics(float fx, float fy, float cx, float cy,
               float w, float h) noexcept
        : fx(fx), fy(fy), cx(cx), cy(cy), width(w), height(h) {}
    Intrinsics() noexcept = default;
};

// ---------------------------------------------------------------------------
// ShapePrior — expected 3D physical size and 1-sigma uncertainty (meters).
//
// Dimension convention follows the world frame used by SceneScape:
//   mu_x = width  (side-to-side extent)
//   mu_y = depth  (front-to-back extent along the object's facing direction)
//   mu_z = height (vertical extent)
//
// sigma = 0 → dimension is unknown; the library substitutes mu * SIGMA_AUTO_FACTOR
//             as a learned wide prior (same heuristic as class_prior.py).
//
// sigma = very large (e.g. 1e6) → also treated as "unknown depth" (FREE_3D).
// ---------------------------------------------------------------------------
struct ShapePrior {
    float mu_x    = 0.5f;   ///< expected physical width  (m)
    float mu_y    = 0.5f;   ///< expected physical depth  (m)
    float mu_z    = 1.7f;   ///< expected physical height (m) — person default

    float sigma_x = 0.0f;   ///< 1-σ width uncertainty  (m, 0 = auto)
    float sigma_y = 0.0f;   ///< 1-σ depth uncertainty  (m, 0 = auto)
    float sigma_z = 0.0f;   ///< 1-σ height uncertainty (m, 0 = auto)

    /// When true, BB width↔mu_x and height↔mu_z; when false, orientation-averaged size.
    bool axis_aware = true;

    /// When sigma = 0, use this fraction of mu as the prior sigma.
    static constexpr float SIGMA_AUTO_FACTOR = 0.40f;

    ShapePrior(float mx, float my, float mz,
               float sx, float sy, float sz,
               bool axis_aware_ = true) noexcept
        : mu_x(mx), mu_y(my), mu_z(mz),
          sigma_x(sx), sigma_y(sy), sigma_z(sz),
          axis_aware(axis_aware_) {}
    ShapePrior() noexcept = default;
};

// ---------------------------------------------------------------------------
// DetectorNoise — detector-level bounding-box localization uncertainty.
// ---------------------------------------------------------------------------
struct DetectorNoise {
    /// 1-sigma edge localization error in pixels.
    /// Typical values: YOLOX-S ≈ 2 px, higher-accuracy detectors ≈ 1 px.
    float sigma_px = 2.0f;

    explicit DetectorNoise(float sigma = 2.0f) noexcept : sigma_px(sigma) {}
};

// ---------------------------------------------------------------------------
// RangeConvention — how a ranging sensor reports the distance to a surface.
//
// SLANT_RANGE       — Euclidean distance from the camera origin to the surface
//                     along the line of sight (the hypotenuse).  Polar-style
//                     sensors (most scanning LiDAR, radar, single-point ToF)
//                     report this directly.
//
// CARTESIAN_DEPTH   — Perpendicular distance from the surface to the camera's
//                     image plane, i.e. the z-coordinate in the camera frame
//                     (the cathetus).  Stereo and structured-light depth
//                     cameras report this — Intel RealSense in particular emits
//                     a Cartesian z-depth map, NOT slant range.
//
// The library internally works in slant range along the center ray.  A
// CARTESIAN_DEPTH measurement z is converted to slant range r via the forward
// (z) component of the unit center ray:  r = z / ray_z.
// ---------------------------------------------------------------------------
enum class RangeConvention : uint8_t {
    SLANT_RANGE     = 0,   ///< distance along the line of sight (hypotenuse)
    CARTESIAN_DEPTH = 1,   ///< perpendicular distance to the image plane (z-depth)
};

// ---------------------------------------------------------------------------
// RangeSensorConfig — per-sensor calibration for ranging modalities.
//
// Create one instance per ranging sensor (ToF, LiDAR, structured light,
// radar, stereo, DNN depth) and reuse across frames.  Range values are
// slant range in meters: Euclidean distance from the camera origin to the
// nearest surface of the object along the ray.
//
// Measurements outside [range_min_m, range_max_m] are discarded and the
// projection falls back to angular-only estimation.
//
// convention selects how the sensor reports distance: CARTESIAN_DEPTH (default,
// perpendicular z-depth as emitted by Intel RealSense and most depth cameras) or
// SLANT_RANGE (distance along the ray, as reported by scanning LiDAR/radar/ToF).
// range_min_m / range_max_m are interpreted in the sensor's native convention
// (the raw reported value is range-checked before any conversion to slant range).
//
// Typical sigma_m values by modality:
//   ToF (consumer)     0.02 – 0.05 m
//   Structured light   0.005 – 0.01 m
//   LiDAR (automotive) 0.01 – 0.03 m
//   Radar              0.10 – 0.50 m
//   Stereo / DNN depth 0.20 – 1.00 m
// ---------------------------------------------------------------------------
struct RangeSensorConfig {
    float sigma_m     = 0.05f;    ///< 1-σ measurement noise (m)
    float range_min_m = 0.0f;     ///< measurements ≤ this are discarded
    float range_max_m = 1.0e6f;   ///< measurements > this are discarded
    RangeConvention convention = RangeConvention::CARTESIAN_DEPTH; ///< distance convention

    RangeSensorConfig() noexcept = default;
    RangeSensorConfig(float sigma, float rmin, float rmax,
                      RangeConvention conv = RangeConvention::CARTESIAN_DEPTH) noexcept
        : sigma_m(sigma), range_min_m(rmin), range_max_m(rmax), convention(conv) {}
};


// ---------------------------------------------------------------------------
// FrustumObservation — output: 3D Gaussian in the CAMERA frame.
//
// Camera frame convention: x = right, y = down, z = forward (OpenCV).
//
// The Gaussian represents the probability distribution over the object's
// center-of-mass location given the observed bounding box, shape prior and
// detector noise, before any terrain or inter-camera constraints are applied.
//
// The depth axis is aligned with the center ray; the lateral axes are aligned
// with the image horizontal and vertical directions (perpendicular to ray).
// This produces a ray-elongated Gaussian when depth is poorly constrained.
//
// To apply terrain or pose constraints the caller should:
//   1. Transform to world frame via transform_to_world().
//   2. Apply the terrain z-constraint as a conditioning step (Phase 2).
//   3. Fuse across cameras in information form (Phase 3a).
// ---------------------------------------------------------------------------
struct FrustumObservation {
    float mu[3]      = {};   ///< position mean in camera frame (m)    [x, y, z]
    float Sigma[9]   = {};   ///< 3×3 covariance, row-major     (m²)  [row0|row1|row2]
    float ray[3]     = {};   ///< unit ray through bb center           [dx, dy, dz]
    float depth_est   = 0.f;  ///< MAP depth estimate along ray  (m)
    float depth_sigma = 0.f;  ///< 1-σ depth uncertainty          (m)
    float depth_lo    = 0.f;  ///< Lower bound on depth (m).
    ///   Meaningful only when at least one axis has BOTH edges unclipped.
    ///   Derived from dim_lo (smallest 1-sigma physical extent of any dimension)
    ///   and the observed angular subtense: dim_lo / (2·tan(α/2)).
    ///   Soft assumption: the detector saw the full object extent on that axis
    ///   (no inter-object occlusion detectable at this stage).
    ///   Value = 0 when all visible axes have a clipped edge — the object could
    ///   be arbitrarily close to the camera.
    float depth_hi    = 0.f;  ///< Upper bound on depth (m).
    ///   Observed bb subtends ≤ true silhouette on every axis, so
    ///   dim_hi / (2·tan(α_obs/2)) ≥ true depth — valid clipped or not.
    ///   Clipping makes the bound looser (larger) but never invalid.
    ///   dim_hi = max(mu_k + sigma_k) over all three dimensions.
    ///   Intersection across both axes; INF only if bb is degenerate.
    float score       = 0.f;  ///< depth-constraint quality  ∈ [0, 1]
    uint8_t edge_valid = 0;   ///< unclipped edges (bit layout = EDGE_* flags)
};

} // namespace fg
