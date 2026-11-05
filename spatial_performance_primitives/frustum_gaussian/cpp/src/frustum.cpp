// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "frustum_gaussian/frustum.hpp"

#include <Eigen/Dense>
#include <algorithm>
#include <cmath>
#include <limits>
#include <tuple>
#include <utility>

namespace fg {

// ============================================================================
// Internal helpers
// ============================================================================

namespace {

using Vec3f = Eigen::Vector3f;
using Mat3f = Eigen::Matrix3f;

constexpr float INF_DEPTH = 1.0e9f;

/// When sigma=0 in the shape prior, substitute mu * this fraction.
constexpr float SIGMA_AUTO_FACTOR = ShapePrior::SIGMA_AUTO_FACTOR;

/// Depth uncertainty at which score = 0.5 (characteristic scene scale).
constexpr float SIGMA_CHAR_M = 30.0f;

// ---------------------------------------------------------------------------
// Resolve effective sigma — substitutes auto-prior when sigma == 0.
// ---------------------------------------------------------------------------
[[nodiscard]] inline float effective_sigma(float mu, float sigma) noexcept {
    return (sigma > 0.0f) ? sigma : (mu * SIGMA_AUTO_FACTOR);
}

// ---------------------------------------------------------------------------
// Auto-detect clipping from image bounds.
// Returns bit-mask where bit=1 means that edge IS clipped.
// ---------------------------------------------------------------------------
[[nodiscard]] uint8_t detect_clipped(const BoundingBox& bb,
                                     const Intrinsics&  K) noexcept {
    constexpr float M = BoundingBox::CLIP_MARGIN_PX;
    uint8_t c = 0;
    if (bb.u_min < M)               c |= EDGE_LEFT;
    if (bb.u_max > K.width  - M)    c |= EDGE_RIGHT;
    if (bb.v_min < M)               c |= EDGE_TOP;
    if (bb.v_max > K.height - M)    c |= EDGE_BOTTOM;
    return c;
}

// ---------------------------------------------------------------------------
// Estimate depth from one axis of the bounding box.
//
// physical_size   — expected object dimension along that axis (meters)
// sigma_physical  — 1-sigma uncertainty in physical size (meters)
// alpha           — measured angular subtense (radians, must be > 0)
// sigma_angular   — 1-sigma uncertainty in alpha (radians)
//
// Returns {depth_est (m), sigma_depth (m)}.
// Returns {INF_DEPTH, INF_DEPTH} when the estimate is unusable.
// ---------------------------------------------------------------------------
[[nodiscard]] std::pair<float, float>
depth_from_angular_size(float physical_size,
                        float sigma_physical,
                        float alpha,
                        float sigma_angular) noexcept {
    if (alpha < 1.0e-5f || physical_size <= 0.0f)
        return {INF_DEPTH, INF_DEPTH};

    // d = physical / (2 * tan(alpha / 2))
    const float half_a   = alpha * 0.5f;
    const float tan_half = std::tan(half_a);
    if (tan_half < 1.0e-7f)
        return {INF_DEPTH, INF_DEPTH};

    const float d = physical_size / (2.0f * tan_half);

    // Uncertainty propagation from physical size uncertainty:
    //   sigma_d_size = sigma_physical / (2 * tan(alpha/2))
    const float sigma_d_size = sigma_physical / (2.0f * tan_half);

    // Uncertainty propagation from angular measurement noise:
    //   d(d)/d(alpha) = -physical / (4 * sin^2(alpha/2))   [take magnitude]
    const float sin_half = std::sin(half_a);
    const float dd_da    = (sin_half > 1.0e-7f)
                         ? (physical_size / (4.0f * sin_half * sin_half))
                         : INF_DEPTH;
    const float sigma_d_angular = dd_da * sigma_angular;

    const float sigma_d = std::sqrt(sigma_d_size    * sigma_d_size +
                                    sigma_d_angular * sigma_d_angular);

    return {d, sigma_d};
}

// ---------------------------------------------------------------------------
// Fuse two independent depth estimates via inverse-variance (information) weighting.
// Returns {d_fused, sigma_fused}.
// ---------------------------------------------------------------------------
[[nodiscard]] std::pair<float, float>
fuse_depths(float d1, float s1,
            float d2, float s2) noexcept {
    const bool ok1 = (s1 < 1.0e8f);
    const bool ok2 = (s2 < 1.0e8f);

    if (ok1 && ok2) {
        const float lam1  = 1.0f / (s1 * s1);
        const float lam2  = 1.0f / (s2 * s2);
        const float lam   = lam1 + lam2;
        return {(lam1 * d1 + lam2 * d2) / lam, 1.0f / std::sqrt(lam)};
    }
    if (ok1) return {d1, s1};
    if (ok2) return {d2, s2};
    return {10.0f, INF_DEPTH};   // fully unconstrained — FREE_3D fallback
}

} // anonymous namespace

// ============================================================================
// project_frustum
// ============================================================================

FrustumObservation project_frustum(const BoundingBox&   bb,
                                   const Intrinsics&    K,
                                   const ShapePrior&    prior,
                                   const DetectorNoise& noise) noexcept {
    FrustumObservation out{};

    // ---- 1. Edge clipping ------------------------------------------------
    const uint8_t clipped = (bb.clipped == BoundingBox::CLIPPED_AUTO)
                          ? detect_clipped(bb, K)
                          : bb.clipped;
    out.edge_valid = (~clipped) & EDGE_ALL;

    const bool lr_valid = !(clipped & EDGE_LEFT)  && !(clipped & EDGE_RIGHT);
    const bool tb_valid = !(clipped & EDGE_TOP)   && !(clipped & EDGE_BOTTOM);

    // ---- 2. Normalized image-plane coordinates ---------------------------
    const float xn_min = (bb.u_min - K.cx) / K.fx;
    const float xn_max = (bb.u_max - K.cx) / K.fx;
    const float yn_min = (bb.v_min - K.cy) / K.fy;   // top    (smaller y)
    const float yn_max = (bb.v_max - K.cy) / K.fy;   // bottom (larger  y)
    const float xn_c   = 0.5f * (xn_min + xn_max);
    const float yn_c   = 0.5f * (yn_min + yn_max);

    // ---- 3. Center ray (camera frame: x=right, y=down, z=forward) --------
    const Vec3f r_hat = Vec3f(xn_c, yn_c, 1.0f).normalized();
    out.ray[0] = r_hat.x();
    out.ray[1] = r_hat.y();
    out.ray[2] = r_hat.z();

    // ---- 4. Shape-prior bounds (orientation-agnostic, sigma-inclusive) -----
    //
    // Without knowing the object's orientation, any of the three physical
    // dimensions [mu_x, mu_y, mu_z] could be subtending the observed angular
    // extent in either the horizontal or vertical image direction.
    //
    // Physical sizes: axis-aware (BB width↔mu_x, height↔mu_z) or
    // orientation-averaged dim_est (when prior.axis_aware is false).
    const float sx = effective_sigma(prior.mu_x, prior.sigma_x);
    const float sy = effective_sigma(prior.mu_y, prior.sigma_y);
    const float sz = effective_sigma(prior.mu_z, prior.sigma_z);

    const float dim_x_lo = std::max(1.0e-3f, prior.mu_x - sx);
    const float dim_x_hi = prior.mu_x + sx;
    const float dim_z_lo = std::max(1.0e-3f, prior.mu_z - sz);
    const float dim_z_hi = prior.mu_z + sz;
    const float dim_lo  = std::max(1.0e-3f,
                              std::min({prior.mu_x - sx,
                                        prior.mu_y - sy,
                                        prior.mu_z - sz}));
    const float dim_hi  = std::max({prior.mu_x + sx,
                                     prior.mu_y + sy,
                                     prior.mu_z + sz});
    const float dim_est = 0.5f * (dim_lo + dim_hi);
    const float sigma_orient    = 0.5f * (dim_hi - dim_lo);
    const float max_sigma_prior = std::max({sx, sy, sz});
    const float sigma_dim       = std::hypot(sigma_orient, max_sigma_prior);
    const bool axis_aware = prior.axis_aware;

    // ---- 5. Angular subtenses (exact, using atan for wide-angle cameras) -
    //
    // Angular measurement uncertainty: two independent edges, each ±sigma_px:
    //   sigma_alpha = sqrt(2) * sigma_px / focal_length
    const float sigma_alpha_x = 1.41421356f * noise.sigma_px / K.fx;
    const float sigma_alpha_y = 1.41421356f * noise.sigma_px / K.fy;

    // Angular extents are computed from raw bb coordinates unconditionally.
    // Clipping does NOT invalidate the upper-bound on depth: a large observed
    // extent — even if the full silhouette is not visible — still constrains how
    // far away the object can be.  Only depth_lo and the depth estimate require
    // both edges to be unclipped (lr_valid / tb_valid gates below).
    const float alpha_x = std::atan(xn_max) - std::atan(xn_min);
    const float alpha_y = std::atan(yn_max) - std::atan(yn_min);

    // Pre-compute tan(alpha/2) for depth-bound calculation below.
    const float tan_x_half = std::tan(alpha_x * 0.5f);
    const float tan_y_half = std::tan(alpha_y * 0.5f);

    // ---- 6. Depth estimates ----------------------------------------------
    float d_x = INF_DEPTH, sd_x = INF_DEPTH, d_y = INF_DEPTH, sd_y = INF_DEPTH;
    if (axis_aware) {
        // Horizontal BB uses width (mu_x); vertical BB uses height (mu_z).
        if (lr_valid && prior.mu_x > 0.0f)
            std::tie(d_x, sd_x) = depth_from_angular_size(
                prior.mu_x, sx, alpha_x, sigma_alpha_x);
        if (tb_valid && prior.mu_z > 0.0f)
            std::tie(d_y, sd_y) = depth_from_angular_size(
                prior.mu_z, sz, alpha_y, sigma_alpha_y);
    } else if (dim_est > 0.0f) {
        if (lr_valid)
            std::tie(d_x, sd_x) = depth_from_angular_size(
                dim_est, sigma_dim, alpha_x, sigma_alpha_x);
        if (tb_valid)
            std::tie(d_y, sd_y) = depth_from_angular_size(
                dim_est, sigma_dim, alpha_y, sigma_alpha_y);
    }

    // ---- 7. Fuse depth estimates (information-form weighting) ------------
    auto [d_est, sigma_depth] = fuse_depths(d_x, sd_x, d_y, sd_y);
    d_est = std::max(d_est, 0.1f);   // clamp to avoid degenerate near-zero

    out.depth_est   = d_est;
    out.depth_sigma = sigma_depth;

    // ---- 8a. Geometric depth bounds --------------------------------------
    //
    // depth_hi — observed bb subtends ≤ true silhouette on every axis.
    // depth_lo — only valid when BOTH edges on an axis are unclipped.
    const float bound_hi_x = axis_aware ? dim_x_hi : dim_hi;
    const float bound_hi_y = axis_aware ? dim_z_hi : dim_hi;
    const float bound_lo_x = axis_aware ? dim_x_lo : dim_lo;
    const float bound_lo_y = axis_aware ? dim_z_lo : dim_lo;
    const float hi_x = (tan_x_half > 1e-7f) ? bound_hi_x / (2.0f * tan_x_half) : INF_DEPTH;
    const float hi_y = (tan_y_half > 1e-7f) ? bound_hi_y / (2.0f * tan_y_half) : INF_DEPTH;

    // Lower bound: only from axes where we observed the full extent.
    const float lo_x = (lr_valid && tan_x_half > 1e-7f) ? bound_lo_x / (2.0f * tan_x_half) : 0.0f;
    const float lo_y = (tb_valid && tan_y_half > 1e-7f) ? bound_lo_y / (2.0f * tan_y_half) : 0.0f;

    // Intersect upper bounds; union lower bounds (tightest near-limit wins).
    out.depth_hi = std::min(hi_x, hi_y);
    out.depth_lo = std::max(lo_x, lo_y);   // 0 if no unclipped axis

    if (out.depth_hi < out.depth_lo)   // inconsistent prior — widen hi to match
        out.depth_hi = out.depth_lo * 2.0f;

    // ---- 8a'. Bounded fallback when the angular depth is unconstrained ----
    //
    // When BOTH image axes are clipped the bounding box fills the frame and no
    // finite-variance angular depth estimate exists (fuse_depths returned its
    // {10 m, INF} placeholder).  The depth is NOT unbounded, however: the object
    // must still lie within [depth_lo, depth_hi].
    //
    // depth_hi is the farthest the object can be while still over-filling the
    // frame — reached when its LARGEST plausible dimension (dim_hi) is exactly
    // subtended by the frame:  dim_hi / (2·tan(alpha_obs/2)).  With both edges
    // clipped depth_lo = 0, so the object lies somewhere in [0, depth_hi].
    //
    // Model the remaining ignorance as a uniform distribution over that interval
    // (maximum entropy on a bounded support) rather than sigma = INF:
    //   mean  = (lo + hi) / 2
    //   sigma = (hi - lo) / sqrt(12)
    // This keeps the ray-elongated Gaussian finite and correctly scaled to the
    // largest-dimension distance limit.
    constexpr float INV_SQRT_12 = 0.28867513f;   // 1 / sqrt(12)
    if (sigma_depth >= 1.0e8f && out.depth_hi < INF_DEPTH) {
        d_est       = std::max(0.5f * (out.depth_lo + out.depth_hi), 0.1f);
        sigma_depth = (out.depth_hi - out.depth_lo) * INV_SQRT_12;
        out.depth_est   = d_est;
        out.depth_sigma = sigma_depth;
    }

    // Quality score: 1 = precisely constrained depth, 0 = unconstrained.
    // Uses a Cauchy-type decay with SIGMA_CHAR_M as the characteristic scale.
    out.score = (SIGMA_CHAR_M * SIGMA_CHAR_M) /
                (SIGMA_CHAR_M * SIGMA_CHAR_M + sigma_depth * sigma_depth);

    // ---- 8b. Position mean: MAP depth along center ray -------------------
    const Vec3f mu_cam = d_est * r_hat;
    out.mu[0] = mu_cam.x();
    out.mu[1] = mu_cam.y();
    out.mu[2] = mu_cam.z();

    // ---- 9. Lateral uncertainty at depth d_est ---------------------------
    //
    // Two contributions per image axis:
    //   (a) Detector edge localization: angular noise projected to lateral dist
    //   (b) Shape prior: per-axis (axis-aware) or orientation-averaged sigma_dim
    const float half_h = axis_aware ? sx * 0.5f : sigma_dim * 0.5f;
    const float half_v = axis_aware ? sz * 0.5f : sigma_dim * 0.5f;
    const float sigma_h = d_est * (noise.sigma_px / K.fx) + half_h;
    const float sigma_v = d_est * (noise.sigma_px / K.fy) + half_v;

    // ---- 10. Orthonormal frame aligned with the center ray ---------------
    //
    // Build {e_h, e_v, e_r} where:
    //   e_r = r_hat (depth axis, along ray)
    //   e_h ≈ camera-right (image horizontal tangent, ⊥ ray)
    //   e_v ≈ camera-down  (image vertical   tangent, ⊥ ray and e_h)
    //
    // Degenerate case: if r_hat is nearly parallel to the camera-up direction
    // (overhead camera pointing straight down), fall back to camera-x axis.
    const Vec3f cam_up = (std::abs(r_hat.y()) > 0.9f)
                       ? Vec3f(1.0f, 0.0f, 0.0f)   // fallback: camera-right
                       : Vec3f(0.0f, -1.0f, 0.0f); // camera-up = -y

    const Vec3f e_h = r_hat.cross(cam_up).normalized();  // image-horizontal ⊥ ray
    const Vec3f e_v = r_hat.cross(e_h);                  // image-vertical   ⊥ ray (already unit)
    // e_r = r_hat

    // ---- 11. 3×3 covariance in camera frame (sum of outer products) ------
    //
    // Sigma = sigma_h^2 * (e_h e_h^T) + sigma_v^2 * (e_v e_v^T) + sigma_d^2 * (e_r e_r^T)
    //
    // This is the eigendecomposition form — guaranteed PSD, minimal FLOP count.
    const Mat3f Sigma_cam =
        (sigma_h * sigma_h) * (e_h * e_h.transpose()) +
        (sigma_v * sigma_v) * (e_v * e_v.transpose()) +
        (sigma_depth * sigma_depth) * (r_hat * r_hat.transpose());

    // Store row-major (Eigen default is column-major, so transpose for row-major)
    Eigen::Map<Eigen::Matrix<float, 3, 3, Eigen::RowMajor>>(out.Sigma) = Sigma_cam;

    return out;
}

// ============================================================================
// project_frustum — range-augmented overload
// ============================================================================

FrustumObservation project_frustum(const BoundingBox&       bb,
                                   const Intrinsics&        K,
                                   const ShapePrior&        prior,
                                   const DetectorNoise&     noise,
                                   float                    range_m,
                                   const RangeSensorConfig& sensor) noexcept {
    // Validate range measurement — discard and fall back to angular-only.
    const bool range_valid = std::isfinite(range_m)
                          && range_m >  sensor.range_min_m
                          && range_m <= sensor.range_max_m;
    if (!range_valid)
        return project_frustum(bb, K, prior, noise);

    // Start from the angular-only result then override depth-dependent fields.
    FrustumObservation out = project_frustum(bb, K, prior, noise);

    // ---- Convert measurement to slant range -----------------------------
    //
    // The library works in slant range along the center ray.  A SLANT_RANGE
    // sensor already reports this.  A CARTESIAN_DEPTH sensor (e.g. Intel
    // RealSense) reports the perpendicular distance to the image plane — the
    // z-coordinate in the camera frame.  Convert it to slant range using the
    // forward (z) component of the unit center ray:
    //   slant = z_depth / ray_z          (since z_depth = slant * ray_z)
    // Validation above used the raw reported value in the sensor's native
    // convention, so range_min_m / range_max_m mean what the datasheet says.
    float range_slant = range_m;
    if (sensor.convention == RangeConvention::CARTESIAN_DEPTH) {
        const float ray_z = out.ray[2];   // forward component of unit ray
        range_slant = (ray_z > 1.0e-6f) ? (range_m / ray_z) : range_m;
    }

    // ---- Range fusion ---------------------------------------------------
    //
    // range_slant = slant range to the nearest surface.
    // Centroid depth along the ray:
    //   d_center = range_slant + dim_est / 2
    // where dim_est is the expected depth extent of the object.
    //
    // Centroid depth uncertainty:
    //   sigma_range_center = sqrt( sensor.sigma_m^2 + (sigma_dim/2)^2 )
    //
    // We then fuse this range-derived centroid estimate with the angular
    // centroid estimate in information form.

    // Reconstruct dim_est / sigma_dim from the prior (same logic as above).
    const float sx = effective_sigma(prior.mu_x, prior.sigma_x);
    const float sy = effective_sigma(prior.mu_y, prior.sigma_y);
    const float sz = effective_sigma(prior.mu_z, prior.sigma_z);
    const float dim_lo  = std::max(1.0e-3f,
                              std::min({prior.mu_x - sx,
                                        prior.mu_y - sy,
                                        prior.mu_z - sz}));
    const float dim_hi  = std::max({prior.mu_x + sx, prior.mu_y + sy, prior.mu_z + sz});
    const float dim_est = 0.5f * (dim_lo + dim_hi);
    const float sigma_orient    = 0.5f * (dim_hi - dim_lo);
    const float max_sigma_prior = std::max({sx, sy, sz});
    const float sigma_dim       = std::hypot(sigma_orient, max_sigma_prior);

    const float d_range       = range_slant + dim_est * 0.5f;
    const float sd_range      = std::hypot(sensor.sigma_m, sigma_dim * 0.5f);

    // Fuse with the angular estimate.
    auto [d_fused, sd_fused] = fuse_depths(out.depth_est, out.depth_sigma,
                                           d_range,       sd_range);
    d_fused = std::max(d_fused, 0.1f);

    // ---- Tighten geometric bounds ---------------------------------------
    out.depth_lo = std::max(out.depth_lo, range_slant);
    out.depth_hi = std::min(out.depth_hi, range_slant + dim_hi);
    if (out.depth_hi < out.depth_lo)
        out.depth_hi = out.depth_lo;

    // Clamp fused centroid to geometric bounds to maintain depth_lo ≤ depth_est ≤ depth_hi.
    d_fused = std::clamp(d_fused, out.depth_lo, out.depth_hi);

    out.depth_est   = d_fused;
    out.depth_sigma = sd_fused;

    // ---- Re-score -------------------------------------------------------
    out.score = (SIGMA_CHAR_M * SIGMA_CHAR_M) /
                (SIGMA_CHAR_M * SIGMA_CHAR_M + sd_fused * sd_fused);

    // ---- Recompute mu and Sigma at fused depth -------------------------
    const Eigen::Map<const Vec3f> r_hat(out.ray);
    const Vec3f mu_cam = d_fused * r_hat;
    out.mu[0] = mu_cam.x();
    out.mu[1] = mu_cam.y();
    out.mu[2] = mu_cam.z();

    const float half_dim_sigma = sigma_dim * 0.5f;
    const float sigma_h = d_fused * (noise.sigma_px / K.fx) + half_dim_sigma;
    const float sigma_v = d_fused * (noise.sigma_px / K.fy) + half_dim_sigma;

    const Vec3f cam_up = (std::abs(r_hat.y()) > 0.9f)
                       ? Vec3f(1.0f, 0.0f, 0.0f)
                       : Vec3f(0.0f, -1.0f, 0.0f);
    const Vec3f e_h = r_hat.cross(cam_up).normalized();
    const Vec3f e_v = r_hat.cross(e_h);

    using RM = Eigen::Matrix<float, 3, 3, Eigen::RowMajor>;
    const Mat3f Sigma_cam =
        (sigma_h   * sigma_h)   * (e_h    * e_h.transpose())    +
        (sigma_v   * sigma_v)   * (e_v    * e_v.transpose())    +
        (sd_fused  * sd_fused)  * (r_hat  * r_hat.transpose());
    Eigen::Map<RM>(out.Sigma) = Sigma_cam;

    return out;
}
// ============================================================================
// project_frustum_3d — oriented 3D bounding box → FrustumObservation
// ============================================================================

FrustumObservation project_frustum_3d(const float       translation_cam[3],
                                      const float       half_extents[3],
                                      const float       rotation_cam[9],
                                      const Intrinsics& K,
                                      const float       body_sigmas[3]) noexcept {
    const Vec3f t(translation_cam[0], translation_cam[1], translation_cam[2]);
    const float he_x = half_extents[0];
    const float he_y = half_extents[1];
    const float he_z = half_extents[2];

    // rotation_cam is R_body_to_cam, row-major: rotation_cam[3*i+j] = R(i,j).
    // Eigen RowMajor mapping interprets layout identically.
    using RM = Eigen::Matrix<float, 3, 3, Eigen::RowMajor>;
    const Eigen::Map<const RM> R(rotation_cam);

    FrustumObservation out{};

    // Degenerate: object at (or behind) camera origin.
    const float d_est = t.norm();
    if (d_est < 1.0e-6f) return out;

    // ---- Center ray -------------------------------------------------------
    const Vec3f r_hat = t / d_est;
    out.ray[0] = r_hat.x();
    out.ray[1] = r_hat.y();
    out.ray[2] = r_hat.z();

    // ---- mu = translation (object center in camera frame) -----------------
    out.mu[0] = t.x();
    out.mu[1] = t.y();
    out.mu[2] = t.z();

    // ---- Support function h(d) = Σ_i he_i · |col_i(R) · d| ---------------
    //
    // This gives the half-width of the oriented box projected onto direction d.
    // Full projected width = 2 * h(d).
    auto support = [&](const Vec3f& d) noexcept {
        return he_x * std::abs(R.col(0).dot(d))
             + he_y * std::abs(R.col(1).dot(d))
             + he_z * std::abs(R.col(2).dot(d));
    };

    // ---- Depth extent of the box along the camera ray ---------------------
    const float h_depth = support(r_hat);

    // ---- Anisotropic covariance in camera frame ---------------------------
    //
    // Sigma_cam = R * diag(σx², σy², σz²) * Rᵀ
    //
    // This naturally represents sensor uncertainty expressed in the object's
    // body frame (e.g. LiDAR: σ_range > σ_lateral, σ_height).  When all
    // body_sigmas are equal the result is σ² I (isotropic), unchanged by R.
    const Vec3f sv(body_sigmas[0], body_sigmas[1], body_sigmas[2]);
    const Mat3f Sigma_cam = R * sv.cwiseProduct(sv).asDiagonal() * R.transpose();
    Eigen::Map<RM>(out.Sigma) = Sigma_cam;

    // ---- Depth sigma: 1-σ of Sigma projected onto camera ray --------------
    //
    // Var(z) = r̂ᵀ Σ r̂ = Σᵢ (body_sigmas[i] * (col_i(R) · r̂))²
    // This is exactly the support function applied to sv-scaled columns.
    float var_depth = 0.0f;
    for (int i = 0; i < 3; ++i) {
        const float proj = R.col(i).dot(r_hat);
        var_depth += body_sigmas[i] * body_sigmas[i] * proj * proj;
    }
    const float sigma_depth = std::sqrt(var_depth);

    // ---- Depth scalars ----------------------------------------------------
    out.depth_est   = d_est;
    out.depth_sigma = sigma_depth;
    // depth_lo / depth_hi cover the box volume ± position uncertainty along ray.
    out.depth_lo = std::max(0.0f, d_est - h_depth - sigma_depth);
    out.depth_hi = d_est + h_depth + sigma_depth;

    // ---- Quality score: tight depth → score near 1 ------------------------
    out.score = (SIGMA_CHAR_M * SIGMA_CHAR_M) /
                (SIGMA_CHAR_M * SIGMA_CHAR_M + sigma_depth * sigma_depth);

    // ---- edge_valid = EDGE_ALL (no image-edge clipping applies) -----------
    out.edge_valid = EDGE_ALL;

    return out;
}

// Isotropic convenience overload — uniform body-frame noise.
FrustumObservation project_frustum_3d(const float       translation_cam[3],
                                      const float       half_extents[3],
                                      const float       rotation_cam[9],
                                      const Intrinsics& K,
                                      float             range_sigma_m) noexcept {
    const float body_sigmas[3] = {range_sigma_m, range_sigma_m, range_sigma_m};
    return project_frustum_3d(translation_cam, half_extents, rotation_cam, K, body_sigmas);
}

// ============================================================================

FrustumObservation transform_to_world(const FrustumObservation& obs_cam,
                                      const float               pose_mat[16]) noexcept {
    // pose_mat is 4×4 row-major homogeneous: [ R | t ; 0 | 1 ]
    // Row layout: [R00 R01 R02 tx | R10 R11 R12 ty | R20 R21 R22 tz | 0 0 0 1]
    // The 3×3 rotation block occupies columns 0-2 of rows 0-2, i.e. every row
    // starts 4 elements apart.  Use OuterStride<4> so Eigen skips the tx/ty/tz
    // column instead of reading 9 contiguous elements (which would consume tx).
    using RM     = Eigen::Matrix<float, 3, 3, Eigen::RowMajor>;
    using Stride = Eigen::OuterStride<4>;
    const Eigen::Map<const RM, 0, Stride> R(pose_mat, Stride(4));
    const Vec3f tvec(pose_mat[3], pose_mat[7], pose_mat[11]);

    const Eigen::Map<const Vec3f> mu_c(obs_cam.mu);
    const Eigen::Map<const RM>    Sigma_c(obs_cam.Sigma);
    const Eigen::Map<const Vec3f> ray_c(obs_cam.ray);

    FrustumObservation out = obs_cam;  // copy scalars (depth, score, edge_valid)

    // mu_world = R * mu_cam + t
    const Vec3f mu_w = R * mu_c + tvec;
    out.mu[0] = mu_w.x();
    out.mu[1] = mu_w.y();
    out.mu[2] = mu_w.z();

    // Sigma_world = R * Sigma_cam * R^T
    const Mat3f Sigma_w = R * Sigma_c * R.transpose();
    Eigen::Map<Eigen::Matrix<float, 3, 3, Eigen::RowMajor>>(out.Sigma) = Sigma_w;

    // ray_world = R * ray_cam   (direction vector, no translation)
    const Vec3f ray_w = R * ray_c;
    out.ray[0] = ray_w.x();
    out.ray[1] = ray_w.y();
    out.ray[2] = ray_w.z();

    return out;
}

} // namespace fg
