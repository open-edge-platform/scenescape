// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "frustum_gaussian/types.hpp"
#include <cstddef>

namespace fg {

// ---------------------------------------------------------------------------
// Single-detection projection.
//
// Maps a 2D bounding box (pixel coords) + camera intrinsics + object shape
// prior into a 3D Gaussian in the camera frame.
//
// Thread-safe; no shared mutable state.  Typically < 5 µs per call on
// modern x86.  Prefer project_frustum_batch() for multi-detection frames.
// ---------------------------------------------------------------------------
FrustumObservation project_frustum(
    const BoundingBox&   bb,
    const Intrinsics&    K,
    const ShapePrior&    prior,
    const DetectorNoise& noise = DetectorNoise{}) noexcept;

// Range-augmented overload.
//
// `range_m` is slant range to the nearest surface of the object (meters).
// If range_m falls outside sensor.range_min_m .. sensor.range_max_m the
// measurement is silently discarded and the result equals the angular-only
// overload above.
FrustumObservation project_frustum(
    const BoundingBox&       bb,
    const Intrinsics&        K,
    const ShapePrior&        prior,
    const DetectorNoise&     noise,
    float                    range_m,
    const RangeSensorConfig& sensor = RangeSensorConfig{}) noexcept;

// ---------------------------------------------------------------------------
// Batch projection — uses Intel TBB parallel_for across detections.
//
// All pointers must point to contiguous arrays of length `n`.
// The camera intrinsics are shared across all detections (single-camera
// batch).  For multi-camera batches call once per camera.
//
// `out` must be caller-allocated (size n).
//
// `ranges` is optional (pass nullptr for angular-only).  When non-null it
// must be length `n`; NaN or values outside sensor.range_min_m ..
// sensor.range_max_m are silently ignored per element.
//
// Thread safety: safe to call concurrently with different (boxes, priors, out)
// arrays; `K`, `noise` and `sensor` are read-only.
// ---------------------------------------------------------------------------
void project_frustum_batch(
    const BoundingBox*       boxes,
    const Intrinsics&        K,
    const ShapePrior*        priors,
    const DetectorNoise&     noise,
    FrustumObservation*      out,
    size_t                   n,
    const float*             ranges = nullptr,
    const RangeSensorConfig& sensor = RangeSensorConfig{}) noexcept;

// ---------------------------------------------------------------------------
// 3D oriented bounding-box projection.
//
// Converts a detector-supplied 3D bounding box (center + half-extents +
// orientation) into a FrustumObservation Gaussian suitable for the FG
// tracking pipeline.  Works with any 3D sensor: LiDAR, radar, stereo,
// monocular-3D DNN, or a foundation model that outputs an oriented 3D BB.
//
// Unlike project_frustum(), the depth is known from the translation rather
// than inferred from angular size, so depth_sigma is tight (= range_sigma_m
// or the ray-projected body_sigma).  The Gaussian covariance captures
// anisotropic detector uncertainty in the object's body frame and rotates
// it to the camera frame via R_body_to_cam.
//
// CENTER CONVENTION
// -----------------
// `translation_cam` must be the GEOMETRIC CENTER of the bounding box —
// i.e. the centroid of all 8 corners — in the camera frame.
//
// This is the nuScenes / Waymo / MMDetection3D / OpenPCDet convention:
//   corners_z = h/2 * [+1, +1, -1, -1, ...]   (symmetric about center)
//
// KITTI-convention monocular detectors (SMOKE, MonoCon, PGD, CenterNet3D, …)
// use bottom-center instead, where corners_z = [0 … h] and the annotated
// translation is the bottom face center.  To convert before calling:
//   center_cam = bottom_center + R @ [0, 0, h/2]
//
// The Python helper fg.from_3d_annotation(center_is_bottom=True) performs
// this conversion automatically.
//
// Parameters
// ----------
// translation_cam   Geometric center of the 3D BB in camera frame (meters).
// half_extents      Half-sizes [a, b, c] in the object's body frame (meters).
//                   Used to compute depth_lo / depth_hi via the box support
//                   function along the camera ray.
// rotation_cam      R_body_to_cam as a row-major 3×3 matrix (9 floats).
//                   Column k is the k-th body axis expressed in camera frame.
// K                 Camera intrinsics (used for ray computation and edge_valid).
// body_sigmas       1-σ position uncertainties [σx, σy, σz] in the body
//                   frame (meters).  The full 3×3 covariance is:
//                     Sigma_cam = R * diag(σx², σy², σz²) * Rᵀ
//                   This encodes anisotropic sensor noise (e.g. LiDAR has
//                   better lateral than range resolution).
// range_sigma_m     Isotropic fallback: used for all body axes when
//                   body_sigmas is not supplied.
//
// Returned fields
// ---------------
// mu          = translation_cam (object center in camera frame)
// Sigma       = R * diag(σx², σy², σz²) * Rᵀ  (camera frame)
// ray         = normalize(translation_cam)
// depth_est   = ‖translation_cam‖
// depth_sigma = 1-σ uncertainty along the ray (= ray^T Sigma ray via Σ)
// depth_lo/hi = box near/far surface ± sigma along ray
// score       = tightness ∈ [0, 1] (1 = perfectly known depth)
// edge_valid  = EDGE_ALL (all constraints from 3D detector, not image edges)
// ---------------------------------------------------------------------------

// Anisotropic body-frame noise.
FrustumObservation project_frustum_3d(
    const float       translation_cam[3],
    const float       half_extents[3],
    const float       rotation_cam[9],
    const Intrinsics& K,
    const float       body_sigmas[3]) noexcept;

// Isotropic convenience overload.
FrustumObservation project_frustum_3d(
    const float       translation_cam[3],
    const float       half_extents[3],
    const float       rotation_cam[9],
    const Intrinsics& K,
    float             range_sigma_m = 0.5f) noexcept;

// ---------------------------------------------------------------------------
// World-frame transform utility.
//
// Applies the 4×4 camera-to-world pose matrix (row-major, homogeneous) to
// rotate mu and Sigma from camera frame to world frame.  ray is also rotated.
// depth_est, depth_sigma, score and edge_valid are preserved unchanged.
//
// `pose_mat` layout (row-major):  [ R | t ]  where R is 3×3 rotation and
//                                  [ 0 | 1 ]  t is 3×1 translation (meters).
// This matches the pose_mat used by SceneScape's CameraPose class.
// ---------------------------------------------------------------------------
FrustumObservation transform_to_world(
    const FrustumObservation& obs_cam,
    const float               pose_mat[16]) noexcept;

// ---------------------------------------------------------------------------
// Convenience header — includes everything.
// ---------------------------------------------------------------------------

} // namespace fg
