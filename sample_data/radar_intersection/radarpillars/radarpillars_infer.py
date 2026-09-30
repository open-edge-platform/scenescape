#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""RadarPillars OpenVINO inference (host preproc + OV BEV/detect IR).

Input: VoD-style float32 (N, 7) = x,y,z,rcs,v_r,v_r_comp,time
   or VIDETEC (N, 5) via videtec_frame_to_pcd().
Output: list of dicts with translation, size, rotation, category, confidence.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

try:
  import openvino as ov
except ImportError:  # pragma: no cover
  ov = None


def videtec_frame_to_pcd(frame: np.ndarray) -> np.ndarray:
  """(N,5) range/doppler/az/el/mag → (N,7) VoD-like radar PCD."""
  from videtec_to_pcd import videtec_to_pcd
  return videtec_to_pcd(frame)


def _voxelize(points, pc_range, voxel_size, max_points, max_voxels):
  if points.shape[0] == 0:
    return (np.zeros((0, max_points, points.shape[1]), np.float32),
            np.zeros((0, 3), np.int32),
            np.zeros((0,), np.int32))
  origin = np.array(pc_range[:3], dtype=np.float32)
  vs = np.array(voxel_size, dtype=np.float32)
  coords = np.floor((points[:, :3] - origin) / vs).astype(np.int32)
  # Keep in-range
  nx = int(round((pc_range[3] - pc_range[0]) / voxel_size[0]))
  ny = int(round((pc_range[4] - pc_range[1]) / voxel_size[1]))
  nz = max(1, int(round((pc_range[5] - pc_range[2]) / voxel_size[2])))
  mask = ((coords[:, 0] >= 0) & (coords[:, 0] < nx) &
          (coords[:, 1] >= 0) & (coords[:, 1] < ny) &
          (coords[:, 2] >= 0) & (coords[:, 2] < nz))
  points = points[mask]
  coords = coords[mask]
  if points.shape[0] == 0:
    return (np.zeros((0, max_points, points.shape[1] if points.ndim == 2 else 7), np.float32),
            np.zeros((0, 3), np.int32),
            np.zeros((0,), np.int32))

  # Group by voxel key
  keys = coords[:, 0] + coords[:, 1] * nx + coords[:, 2] * nx * ny
  order = np.argsort(keys)
  keys_s = keys[order]
  points = points[order]
  coords = coords[order]
  uniq, start, counts = np.unique(keys_s, return_index=True, return_counts=True)
  if uniq.shape[0] > max_voxels:
    uniq = uniq[:max_voxels]
    start = start[:max_voxels]
    counts = counts[:max_voxels]
  nfeat = points.shape[1]
  voxels = np.zeros((len(uniq), max_points, nfeat), dtype=np.float32)
  num_points = np.zeros((len(uniq),), dtype=np.int32)
  coors = np.zeros((len(uniq), 3), dtype=np.int32)
  for i, (s, c) in enumerate(zip(start, counts)):
    take = min(int(c), max_points)
    voxels[i, :take] = points[s:s + take]
    num_points[i] = take
    coors[i] = coords[s]
  return voxels, coors, num_points


def _pillar_vfe(voxels, num_points, weights, pc_range, voxel_size, vfe_compiled=None):
  """Simplified PillarVFE with absolute xyz + velocity decomp + PFN max-pool.

  When ``vfe_compiled`` is an OpenVINO CompiledModel for the fused linear+BN+ReLU
  IR, the affine runs on OV; max-pool over points stays on the host.
  """
  if voxels.shape[0] == 0:
    return np.zeros((0, 32), dtype=np.float32)
  pts = voxels.copy()
  for i in range(pts.shape[0]):
    n = int(num_points[i])
    if n < pts.shape[1]:
      pts[i, n:] = 0

  x = pts[:, :, 0:1]
  y = pts[:, :, 1:2]
  z = pts[:, :, 2:3]
  rcs = pts[:, :, 3:4]
  vr = pts[:, :, 4:5]
  vr_comp = pts[:, :, 5:6]
  time = pts[:, :, 6:7]
  phi = np.arctan2(y, x + 1e-6)
  vx = vr_comp * np.cos(phi)
  vy = vr_comp * np.sin(phi)
  fmean = []
  for i in range(pts.shape[0]):
    n = max(int(num_points[i]), 1)
    fmean.append(pts[i, :n, :3].mean(axis=0))
  fmean = np.asarray(fmean, dtype=np.float32).reshape(-1, 1, 3)
  xc = x - fmean[:, :, 0:1]
  yc = y - fmean[:, :, 1:2]
  zc = z - fmean[:, :, 2:3]
  origin = np.array(pc_range[:3], dtype=np.float32)
  vs = np.array(voxel_size, dtype=np.float32)
  vox_c = np.zeros((pts.shape[0], 1, 3), dtype=np.float32)
  for i in range(pts.shape[0]):
    n = max(int(num_points[i]), 1)
    cidx = np.floor((pts[i, 0, :3] - origin) / vs)
    vox_c[i, 0] = (cidx + 0.5) * vs + origin
  xp = x - vox_c[:, :, 0:1]
  yp = y - vox_c[:, :, 1:2]
  zp = z - vox_c[:, :, 2:3]
  feats = np.concatenate(
    [x, y, z, rcs, vr, vr_comp, time, xc, yc, zc, xp, yp, zp, vx, vy], axis=-1)
  V, P, C = feats.shape
  flat = feats.reshape(V * P, C)
  if vfe_compiled is not None:
    out = np.array(vfe_compiled([flat])[0], dtype=np.float32).reshape(V, P, -1)
  else:
    w = weights["vfe.pfn_layers.0.linear.weight"]  # (32, 15)
    if feats.shape[-1] != w.shape[1]:
      raise RuntimeError(f"VFE feature dim {feats.shape[-1]} != weight in {w.shape[1]}")
    out = flat @ w.T
    gamma = weights["vfe.pfn_layers.0.norm.weight"]
    beta = weights["vfe.pfn_layers.0.norm.bias"]
    mean = weights["vfe.pfn_layers.0.norm.running_mean"]
    var = weights["vfe.pfn_layers.0.norm.running_var"]
    out = (out - mean) / np.sqrt(var + 1e-3)
    out = out * gamma + beta
    out = np.maximum(out, 0)
    out = out.reshape(V, P, -1)
  pillar = np.zeros((V, out.shape[-1]), dtype=np.float32)
  for i in range(V):
    n = max(int(num_points[i]), 1)
    pillar[i] = out[i, :n].max(axis=0)
  return pillar


def _pillar_attention(pillar_features, weights, attn_compiled=None):
  """Single-head PillarAttention (batch_size=1).

  When ``attn_compiled`` is set, run the OpenVINO attention IR; otherwise numpy.
  """
  if pillar_features.shape[0] == 0:
    return pillar_features
  if attn_compiled is not None:
    x = pillar_features.astype(np.float32)[None, ...]  # (1, N, 32)
    y = np.array(attn_compiled([x])[0], dtype=np.float32)
    return y.reshape(pillar_features.shape)
  x = pillar_features  # (N, 32)
  in_w = weights["backbone_3d.attn.in_proj_weight"]
  in_b = weights["backbone_3d.attn.in_proj_bias"]
  out_w = weights["backbone_3d.attn.out_proj.weight"]
  out_b = weights["backbone_3d.attn.out_proj.bias"]
  qkv = x @ in_w.T + in_b
  E = x.shape[1]
  q, k, v = np.split(qkv, 3, axis=-1)
  scale = 1.0 / math.sqrt(E)
  logits = q @ k.T * scale
  logits = logits - logits.max(axis=-1, keepdims=True)
  attn = np.exp(logits)
  attn = attn / (attn.sum(axis=-1, keepdims=True) + 1e-9)
  y = attn @ v
  y = y @ out_w.T + out_b
  y = x + y
  y = _layernorm(y, weights["backbone_3d.norm1.weight"], weights["backbone_3d.norm1.bias"])
  ffn0_w = weights["backbone_3d.ffn.0.weight"]
  ffn0_b = weights["backbone_3d.ffn.0.bias"]
  ffn2_w = weights["backbone_3d.ffn.2.weight"]
  ffn2_b = weights["backbone_3d.ffn.2.bias"]
  h = y @ ffn0_w.T + ffn0_b
  h = 0.5 * h * (1.0 + np.tanh(math.sqrt(2 / math.pi) * (h + 0.044715 * h ** 3)))
  h = h @ ffn2_w.T + ffn2_b
  y = _layernorm(y + h, weights["backbone_3d.norm2.weight"], weights["backbone_3d.norm2.bias"])
  return y.astype(np.float32)


def _layernorm(x, weight, bias, eps=1e-5):
  mean = x.mean(axis=-1, keepdims=True)
  var = x.var(axis=-1, keepdims=True)
  return ((x - mean) / np.sqrt(var + eps)) * weight + bias


def _scatter(pillar_features, coors, nx, ny, channels):
  canvas = np.zeros((channels, ny, nx), dtype=np.float32)
  for i in range(pillar_features.shape[0]):
    x_i, y_i = int(coors[i, 0]), int(coors[i, 1])
    if 0 <= x_i < nx and 0 <= y_i < ny:
      canvas[:, y_i, x_i] = pillar_features[i]
  return canvas[np.newaxis, ...]  # (1, C, H, W)


def _generate_anchors(cfg):
  """Generate anchors on feature map (H/stride, W/stride)."""
  pc = cfg["point_cloud_range"]
  vs = cfg["voxel_size"]
  nx = int(round((pc[3] - pc[0]) / vs[0]))
  ny = int(round((pc[4] - pc[1]) / vs[1]))
  stride = int(cfg["feature_map_stride"])
  fx, fy = nx // stride, ny // stride
  xs = np.linspace(pc[0] + vs[0] * stride / 2, pc[3] - vs[0] * stride / 2, fx)
  ys = np.linspace(pc[1] + vs[1] * stride / 2, pc[4] - vs[1] * stride / 2, fy)
  # OpenPCDet grid: meshgrid indexing
  xx, yy = np.meshgrid(xs, ys, indexing="xy")
  anchors = []
  for sizes, z0 in zip(cfg["anchor_sizes"], cfg["anchor_bottom_heights"]):
    for rot in cfg["anchor_rotations"]:
      a = np.stack([
        xx.reshape(-1),
        yy.reshape(-1),
        np.full(xx.size, z0 + sizes[2] / 2.0),
        np.full(xx.size, sizes[0]),
        np.full(xx.size, sizes[1]),
        np.full(xx.size, sizes[2]),
        np.full(xx.size, rot),
      ], axis=-1)
      anchors.append(a)
  # order: per class then rotation → shape (fy, fx, num_anchors, 7) matching head layout
  # Head layout: num_anchors_per_location = 3 classes * 2 rots = 6, stacked on channel
  return np.stack(anchors, axis=-2).reshape(fy, fx, len(anchors), 7).astype(np.float32)


def _decode_boxes(box_preds, anchors, dir_preds, dir_offset, num_dir_bins):
  """ResidualCoder-style decode (simplified).

  Accepts ``(H, W, A, *)`` or flat ``(N, *)`` for box/anchors (7) and dir (2).
  """
  xa, ya, za, dx, dy, dz, ra = np.split(anchors, 7, axis=-1)
  xt, yt, zt, dxt, dyt, dzt, rt = np.split(box_preds, 7, axis=-1)
  diagonal = np.sqrt(dx ** 2 + dy ** 2)
  xg = xt * diagonal + xa
  yg = yt * diagonal + ya
  zg = zt * dz + za
  dxg = np.exp(dxt) * dx
  dyg = np.exp(dyt) * dy
  dzg = np.exp(dzt) * dz
  rg = rt + ra
  dir_cls = np.argmax(dir_preds, axis=-1)
  period = 2 * np.pi / num_dir_bins
  rg_lim = rg - dir_offset
  rg_lim = rg_lim - np.floor(rg_lim / period + 0.5) * period
  # dir_cls is (...,) — broadcast to match rg's trailing singleton from split
  rg = rg_lim + dir_offset + period * dir_cls[..., None]
  return np.concatenate([xg, yg, zg, dxg, dyg, dzg, rg], axis=-1)


def _logit_threshold(score_threshold: float) -> float:
  """Minimum logit such that sigmoid(logit) >= score_threshold."""
  thr = float(score_threshold)
  thr = min(max(thr, 1e-6), 1.0 - 1e-6)
  return float(math.log(thr / (1.0 - thr)))


def _postprocess_heads(cls_preds, box_preds, dir_preds, anchors, cfg) -> list[dict]:
  """Score-gated decode + NMS (matches C++ radarpillars runtime).

  Only decodes anchors whose best-class logit clears the score threshold,
  avoiding a full 240k-box decode on sparse radar.
  """
  # (1, C, H, W) → (H, W, A, ...)
  def rearrange(pred, per_anchor):
    p = pred[0].transpose(1, 2, 0)  # H W C
    h, w, c = p.shape
    return p.reshape(h, w, c // per_anchor, per_anchor)

  cls = rearrange(cls_preds, 3)
  box = rearrange(box_preds, 7)
  direction = rearrange(dir_preds, 2)
  if anchors.shape[0] != cls.shape[0] or anchors.shape[1] != cls.shape[1]:
    anchors = _generate_anchors(cfg)

  # Best class via logits (equiv to sigmoid-then-argmax); gate before decode.
  best_cls = cls.argmax(axis=-1)
  best_logit = cls.max(axis=-1)
  thr = float(cfg.get("score_threshold", 0.1))
  logit_thr = _logit_threshold(thr)
  mask = best_logit >= logit_thr
  if not np.any(mask):
    return []

  box_m = box[mask]
  anc_m = anchors[mask]
  dir_m = direction[mask]
  cls_m = best_cls[mask]
  # Stable sigmoid for survivors only
  scores_m = 1.0 / (1.0 + np.exp(-best_logit[mask]))
  decoded = _decode_boxes(box_m, anc_m, dir_m, cfg["dir_offset"], cfg["num_dir_bins"])
  if decoded.ndim > 2:
    decoded = decoded.reshape(-1, 7)
  else:
    decoded = decoded.reshape(-1, 7)

  keep = _nms(decoded, scores_m, float(cfg.get("nms_thresh", 0.1)))
  names = cfg["class_names"]
  objects = []
  for idx, k in enumerate(keep):
    b = decoded[k]
    cat = names[int(cls_m[k])] if int(cls_m[k]) < len(names) else "vehicle"
    objects.append({
      "id": idx + 1,
      "category": cat,
      "confidence": float(scores_m[k]),
      "translation": [float(b[0]), float(b[1]), float(b[2])],
      "size": [float(b[3]), float(b[4]), float(b[5])],
      "rotation": _yaw_to_quat(float(b[6])),
    })
  return objects


def _nms(boxes, scores, thresh, top_k=100):
  if boxes.shape[0] == 0:
    return np.array([], dtype=np.int64)
  order = scores.argsort()[::-1]
  keep = []
  while order.size > 0 and len(keep) < top_k:
    i = order[0]
    keep.append(i)
    if order.size == 1:
      break
    rest = order[1:]
    # BEV IoU
    xx1 = np.maximum(boxes[i, 0] - boxes[i, 3] / 2, boxes[rest, 0] - boxes[rest, 3] / 2)
    yy1 = np.maximum(boxes[i, 1] - boxes[i, 4] / 2, boxes[rest, 1] - boxes[rest, 4] / 2)
    xx2 = np.minimum(boxes[i, 0] + boxes[i, 3] / 2, boxes[rest, 0] + boxes[rest, 3] / 2)
    yy2 = np.minimum(boxes[i, 1] + boxes[i, 4] / 2, boxes[rest, 1] + boxes[rest, 4] / 2)
    w = np.maximum(0, xx2 - xx1)
    h = np.maximum(0, yy2 - yy1)
    inter = w * h
    area_i = boxes[i, 3] * boxes[i, 4]
    area_r = boxes[rest, 3] * boxes[rest, 4]
    iou = inter / (area_i + area_r - inter + 1e-6)
    order = rest[iou <= thresh]
  return np.array(keep, dtype=np.int64)


def _yaw_to_quat(yaw: float) -> list[float]:
  half = yaw / 2.0
  return [0.0, 0.0, float(math.sin(half)), float(math.cos(half))]


def _ov_compile(core, model_path: str | Path, device: str):
  """Compile for online single-stream inference (LATENCY hint when supported)."""
  path = str(model_path)
  try:
    from openvino import properties
    cfg = {
      properties.hint.performance_mode: properties.hint.PerformanceMode.LATENCY,
    }
    return core.compile_model(path, device, cfg)
  except Exception:
    return core.compile_model(path, device)


class RadarPillarsOV:
  def __init__(self, config_path: str | Path, device: str = "CPU"):
    if ov is None:
      raise RuntimeError("openvino is required")
    self.config_path = Path(config_path)
    self.cfg = json.loads(self.config_path.read_text())
    model_dir = self.config_path.parent
    self.preproc = dict(np.load(model_dir / self.cfg["preproc_weights"]))
    core = ov.Core()
    # Optional per-stage devices (VIDETEC: BEV on GPU when present; preproc stays CPU).
    bev_device = str(self.cfg.get("bev_device") or device)
    preproc_device = str(self.cfg.get("preproc_device") or device)
    self.compiled = _ov_compile(core, model_dir / self.cfg["nn_model"], bev_device)
    self.vfe_compiled = None
    self.attn_compiled = None
    if self.cfg.get("vfe_linear_model"):
      self.vfe_compiled = _ov_compile(
        core, model_dir / self.cfg["vfe_linear_model"], preproc_device)
    if self.cfg.get("attention_model"):
      self.attn_compiled = _ov_compile(
        core, model_dir / self.cfg["attention_model"], preproc_device)
    self.anchors = _generate_anchors(self.cfg)
    self.device = device
    self.bev_device = bev_device
    self.preproc_device = preproc_device

  def infer(self, points: np.ndarray) -> list[dict]:
    cfg = self.cfg
    voxels, coors, num_points = _voxelize(
      points, cfg["point_cloud_range"], cfg["voxel_size"],
      cfg["max_points_per_voxel"], cfg["max_voxels"])
    pillars = _pillar_vfe(
      voxels, num_points, self.preproc,
      cfg["point_cloud_range"], cfg["voxel_size"],
      vfe_compiled=self.vfe_compiled)
    if pillars.shape[0] == 0:
      return []
    # Fix VFE channel mismatch: pad/truncate to 32
    if pillars.shape[1] != cfg["bev_channels"]:
      out = np.zeros((pillars.shape[0], cfg["bev_channels"]), np.float32)
      n = min(pillars.shape[1], cfg["bev_channels"])
      out[:, :n] = pillars[:, :n]
      pillars = out
    pillars = _pillar_attention(pillars, self.preproc, attn_compiled=self.attn_compiled)
    nx, ny, _ = cfg["grid_size"]
    spatial = _scatter(pillars, coors, nx, ny, cfg["bev_channels"])
    result = self.compiled([spatial])
    # OV returns ConstOutput→tensor map; materialize as numpy.
    outs = []
    if hasattr(result, "values"):
      for t in result.values():
        outs.append(np.array(t))
    else:
      outs = [np.array(t) for t in result]
    cls_preds = box_preds = dir_preds = None
    for a in outs:
      if a.ndim != 4:
        continue
      c = a.shape[1]
      if c == 18:
        cls_preds = a
      elif c == 42:
        box_preds = a
      elif c == 12:
        dir_preds = a
    if cls_preds is None or box_preds is None or dir_preds is None:
      if len(outs) < 3:
        raise RuntimeError(f"Unexpected OV outputs: {[o.shape for o in outs]}")
      cls_preds, box_preds, dir_preds = outs[0], outs[1], outs[2]
    return _postprocess_heads(cls_preds, box_preds, dir_preds, self.anchors, cfg)
