# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Vendored/adapted from scenescape-v2-architecture frustum-gaussian
# benchmarks/numpy_variant.py. See NOTICE for provenance requirements.
"""
Pure-numpy reimplementation of project_frustum_batch.

Mirrors the math in frustum.cpp. No C extension calls.
"""

from __future__ import annotations
import numpy as np

SIGMA_AUTO_FACTOR = 0.40
SIGMA_CHAR_M      = 30.0
INF_DEPTH         = 1.0e9
CLIP_MARGIN_PX    = 3.0

EDGE_LEFT   = 0x01
EDGE_RIGHT  = 0x02
EDGE_TOP    = 0x04
EDGE_BOTTOM = 0x08
EDGE_ALL    = 0x0F


def _auto_clip(u0, v0, u1, v1, width, height, margin):
  """Auto-detect clipped edges when clipped mask is 0xFF."""
  clip = np.zeros(u0.shape[0], np.uint8)
  clip |= np.where(u0 < margin, EDGE_LEFT, 0).astype(np.uint8)
  clip |= np.where(u1 > width - margin, EDGE_RIGHT, 0).astype(np.uint8)
  clip |= np.where(v0 < margin, EDGE_TOP, 0).astype(np.uint8)
  clip |= np.where(v1 > height - margin, EDGE_BOTTOM, 0).astype(np.uint8)
  return clip


def _eff_sigma(mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
  """Return sigma, substituting SIGMA_AUTO_FACTOR * mu where sigma == 0."""
  return np.where(sigma > 0, sigma, mu * SIGMA_AUTO_FACTOR)


def project_frustum_batch_numpy(
  boxes:     np.ndarray,  # (N,4) float32 [u_min, v_min, u_max, v_max]
  intrinsics: np.ndarray, # (4,)  float32 [fx, fy, cx, cy]
  img_size:  np.ndarray,  # (2,)  float32 [width, height]
  priors:    np.ndarray,  # (N,6) float32 [mu_x,mu_y,mu_z, sx,sy,sz]
  sigma_px:  float = 2.0,
  clipped:   np.ndarray | None = None,  # (N,) uint8, 0xFF = auto
  axis_aware: bool | np.ndarray = True,
) -> dict[str, np.ndarray]:
  N = len(boxes)
  if N == 0:
    return {
      "mu":          np.empty((0, 3), np.float32),
      "Sigma":       np.empty((0, 3, 3), np.float32),
      "ray":         np.empty((0, 3), np.float32),
      "depth_est":   np.empty(0, np.float32),
      "depth_sigma": np.empty(0, np.float32),
      "depth_lo":    np.empty(0, np.float32),
      "depth_hi":    np.empty(0, np.float32),
      "score":       np.empty(0, np.float32),
      "edge_valid":  np.empty(0, np.uint8),
    }

  fx, fy, cx, cy = intrinsics.astype(np.float64)
  W, H = img_size.astype(np.float64)
  M = CLIP_MARGIN_PX

  u0 = boxes[:, 0].astype(np.float64)
  v0 = boxes[:, 1].astype(np.float64)
  u1 = boxes[:, 2].astype(np.float64)
  v1 = boxes[:, 3].astype(np.float64)

  mu_x = priors[:, 0].astype(np.float64)
  mu_y = priors[:, 1].astype(np.float64)
  mu_z = priors[:, 2].astype(np.float64)
  sx   = _eff_sigma(mu_x, priors[:, 3].astype(np.float64))
  sy   = _eff_sigma(mu_y, priors[:, 4].astype(np.float64))
  sz   = _eff_sigma(mu_z, priors[:, 5].astype(np.float64))

  if isinstance(axis_aware, (bool, np.bool_)) or np.ndim(axis_aware) == 0:
    aa = np.full(N, bool(axis_aware), dtype=bool)
  else:
    aa = np.asarray(axis_aware, dtype=bool)
    if aa.shape != (N,):
      raise ValueError(f"axis_aware must be bool or shape (N,), got {aa.shape}")

  # ---- 1. Edge clipping ---------------------------------------------------
  if clipped is None:
    clip = np.zeros(N, np.uint8)
    clip |= np.where(u0 < M,     EDGE_LEFT,   0).astype(np.uint8)
    clip |= np.where(u1 > W - M, EDGE_RIGHT,  0).astype(np.uint8)
    clip |= np.where(v0 < M,     EDGE_TOP,    0).astype(np.uint8)
    clip |= np.where(v1 > H - M, EDGE_BOTTOM, 0).astype(np.uint8)
  else:
    clip = np.where(clipped == 0xFF,
                    _auto_clip(u0, v0, u1, v1, W, H, M), clipped).astype(np.uint8)

  edge_valid = (~clip & 0x0F).astype(np.uint8)
  lr_valid = ((clip & EDGE_LEFT) == 0) & ((clip & EDGE_RIGHT)  == 0)
  tb_valid = ((clip & EDGE_TOP)  == 0) & ((clip & EDGE_BOTTOM) == 0)

  # ---- 2. Normalized coords -----------------------------------------------
  xn_min = (u0 - cx) / fx
  xn_max = (u1 - cx) / fx
  yn_min = (v0 - cy) / fy
  yn_max = (v1 - cy) / fy
  xn_c   = 0.5 * (xn_min + xn_max)
  yn_c   = 0.5 * (yn_min + yn_max)

  # ---- 3. Center ray ------------------------------------------------------
  rx = xn_c
  ry = yn_c
  rz = np.ones(N, np.float64)
  rlen = np.sqrt(rx*rx + ry*ry + rz*rz)
  rx /= rlen;  ry /= rlen;  rz /= rlen

  # ---- 4. Physical sizes (axis-aware and orientation-averaged) ------------
  # Axis-aware: image-horizontal BB ↔ width (mu_x); image-vertical ↔ height
  # (mu_z). Orientation-averaged dim_est is better when yaw is unknown.
  dim_x_lo = np.maximum(1e-3, mu_x - sx)
  dim_x_hi = mu_x + sx
  dim_z_lo = np.maximum(1e-3, mu_z - sz)
  dim_z_hi = mu_z + sz
  dim_lo = np.maximum(1e-3, np.minimum.reduce([mu_x - sx, mu_y - sy, mu_z - sz]))
  dim_hi = np.maximum.reduce([mu_x + sx, mu_y + sy, mu_z + sz])
  dim_est = 0.5 * (dim_lo + dim_hi)
  sigma_orient = 0.5 * (dim_hi - dim_lo)
  sigma_dim = np.hypot(sigma_orient, np.maximum.reduce([sx, sy, sz]))

  # ---- 5. Angular half-subtenses ------------------------------------------
  alpha_x = np.arctan(xn_max) - np.arctan(xn_min)
  alpha_y = np.arctan(yn_max) - np.arctan(yn_min)
  alpha_x = np.maximum(alpha_x, 0.0)
  alpha_y = np.maximum(alpha_y, 0.0)

  sigma_angular_x = (sigma_px / fx) / (1.0 + xn_c**2)
  sigma_angular_y = (sigma_px / fy) / (1.0 + yn_c**2)

  # ---- 6. Depth from angular size -----------------------------------------
  tan_x = np.tan(0.5 * alpha_x)
  tan_y = np.tan(0.5 * alpha_y)

  def _depth_sigma(mu_phys, sig_phys, alpha, sigma_ang):
    half_a  = 0.5 * alpha
    tan_h   = np.maximum(np.tan(half_a), 1e-7)
    sin_h   = np.sin(half_a)
    d       = mu_phys / (2.0 * tan_h)
    sd_size = sig_phys / (2.0 * tan_h)
    dd_da   = np.where(sin_h > 1e-7,
                       mu_phys / (4.0 * sin_h * sin_h), INF_DEPTH)
    sd_ang  = dd_da * sigma_ang
    return d, np.sqrt(sd_size**2 + sd_ang**2)

  valid_x = alpha_x > 1e-5
  valid_y = alpha_y > 1e-5

  dx_aa, sdx_aa = _depth_sigma(mu_x, sx, alpha_x, sigma_angular_x)
  dy_aa, sdy_aa = _depth_sigma(mu_z, sz, alpha_y, sigma_angular_y)
  dx_avg, sdx_avg = _depth_sigma(dim_est, sigma_dim, alpha_x, sigma_angular_x)
  dy_avg, sdy_avg = _depth_sigma(dim_est, sigma_dim, alpha_y, sigma_angular_y)

  dx = np.where(aa, dx_aa, dx_avg)
  sdx = np.where(aa, sdx_aa, sdx_avg)
  dy = np.where(aa, dy_aa, dy_avg)
  sdy = np.where(aa, sdy_aa, sdy_avg)

  dx  = np.where(valid_x, dx,  INF_DEPTH)
  sdx = np.where(valid_x, sdx, INF_DEPTH)
  dy  = np.where(valid_y, dy,  INF_DEPTH)
  sdy = np.where(valid_y, sdy, INF_DEPTH)

  # ---- 7. Fuse depths (information-form) ----------------------------------
  ok_x = sdx < 1e8
  ok_y = sdy < 1e8
  lam_x = np.where(ok_x, 1.0 / (sdx * sdx), 0.0)
  lam_y = np.where(ok_y, 1.0 / (sdy * sdy), 0.0)
  lam   = lam_x + lam_y
  d_est   = np.where(lam > 0,
                     (lam_x * dx + lam_y * dy) / lam,
                     np.where(ok_x, dx, np.where(ok_y, dy, 10.0)))
  s_depth = np.where(lam > 0,
                     1.0 / np.sqrt(np.maximum(lam, 1e-30)),
                     np.where(ok_x, sdx, np.where(ok_y, sdy, INF_DEPTH)))

  # ---- 8a. Depth bounds ---------------------------------------------------
  hi_x_aa = np.where(tan_x > 1e-7, dim_x_hi / (2.0 * tan_x), INF_DEPTH)
  hi_y_aa = np.where(tan_y > 1e-7, dim_z_hi / (2.0 * tan_y), INF_DEPTH)
  lo_x_aa = np.where(lr_valid & (tan_x > 1e-7), dim_x_lo / (2.0 * tan_x), 0.0)
  lo_y_aa = np.where(tb_valid & (tan_y > 1e-7), dim_z_lo / (2.0 * tan_y), 0.0)
  hi_x_avg = np.where(tan_x > 1e-7, dim_hi / (2.0 * tan_x), INF_DEPTH)
  hi_y_avg = np.where(tan_y > 1e-7, dim_hi / (2.0 * tan_y), INF_DEPTH)
  lo_x_avg = np.where(lr_valid & (tan_x > 1e-7), dim_lo / (2.0 * tan_x), 0.0)
  lo_y_avg = np.where(tb_valid & (tan_y > 1e-7), dim_lo / (2.0 * tan_y), 0.0)
  hi_x = np.where(aa, hi_x_aa, hi_x_avg)
  hi_y = np.where(aa, hi_y_aa, hi_y_avg)
  lo_x = np.where(aa, lo_x_aa, lo_x_avg)
  lo_y = np.where(aa, lo_y_aa, lo_y_avg)
  depth_hi = np.minimum(hi_x, hi_y)
  depth_lo = np.maximum(lo_x, lo_y)
  depth_hi = np.where(depth_hi < depth_lo, depth_lo * 2.0, depth_hi)

  # ---- 8b. Score ----------------------------------------------------------
  score = (SIGMA_CHAR_M**2) / (SIGMA_CHAR_M**2 + s_depth**2)

  # ---- 8c. Position mean --------------------------------------------------
  # mu = d_est * r_hat
  mu_cam = np.stack([rx * d_est, ry * d_est, rz * d_est], axis=1)

  # ---- 9. Lateral sigma ---------------------------------------------------
  sigma_lat_x = d_est * (sigma_px / fx) + np.where(aa, sx, sigma_dim) * 0.5
  sigma_lat_y = d_est * (sigma_px / fy) + np.where(aa, sz, sigma_dim) * 0.5

  # ---- 10. Orthonormal frame aligned with center ray ----------------------
  # e_h: image-horizontal tangent (perp to ray in xz-plane)
  eh = np.stack([ rz, np.zeros(N), -rx], axis=1)
  eh_len = np.linalg.norm(eh, axis=1, keepdims=True)
  # Fallback when ray is nearly vertical
  fallback_mask = (eh_len[:, 0] < 1e-6)
  eh = np.where(fallback_mask[:, None],
                np.array([[0, 0, 1]], dtype=np.float64), eh / np.maximum(eh_len, 1e-12))
  # e_v: image-vertical tangent = r_hat x e_h
  ev = np.cross(np.stack([rx, ry, rz], axis=1), eh)
  ev_len = np.linalg.norm(ev, axis=1, keepdims=True)
  ev = ev / np.maximum(ev_len, 1e-12)

  # ---- 11. 3x3 covariance (outer products) --------------------------------
  # Sigma = sh^2 eh eh' + sv^2 ev ev' + sd^2 r r'
  sh2 = (sigma_lat_x ** 2)[:, None, None]
  sv2 = (sigma_lat_y ** 2)[:, None, None]
  sd2 = (s_depth      ** 2)[:, None, None]

  r_hat = np.stack([rx, ry, rz], axis=1)
  Sigma = (sh2 * (eh[:, :, None] * eh[:, None, :]) +
           sv2 * (ev[:, :, None] * ev[:, None, :]) +
           sd2 * (r_hat[:, :, None] * r_hat[:, None, :]))

  return {
    "mu":          mu_cam.astype(np.float32),
    "Sigma":       Sigma.astype(np.float32),
    "ray":         r_hat.astype(np.float32),
    "depth_est":   d_est.astype(np.float32),
    "depth_sigma": s_depth.astype(np.float32),
    "depth_lo":    depth_lo.astype(np.float32),
    "depth_hi":    depth_hi.astype(np.float32),
    "score":       score.astype(np.float32),
    "edge_valid":  edge_valid,
  }
