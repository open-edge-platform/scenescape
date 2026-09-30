#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export RadarPillars PillarVFE + PillarAttention slices to OpenVINO IR.

Stage 2b: move matmul-heavy host preproc onto OpenVINO (oneDNN). Feature
construction (15-d) and max-pool over points stay on the host for VFE; this
exports:

  * ``radarpillars_vfe_linear`` — Linear(15→32) + BatchNorm + ReLU on flat
    ``(V*P, 15)`` (dynamic V*P)
  * ``radarpillars_attention`` — single-head PillarAttention + FFN on
    ``(1, N, 32)`` (dynamic N)

Reads existing ``radarpillars_preproc_weights.npz`` (no PyTorch ckpt required).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class VfeLinear(nn.Module):
  """Host ``_pillar_vfe`` affine with BN fused into Linear+bias + ReLU."""

  def __init__(self, weight: np.ndarray, bn_w, bn_b, bn_mean, bn_var, eps: float = 1e-3):
    super().__init__()
    out_c, in_c = weight.shape
    scale = bn_w / np.sqrt(bn_var + eps)
    w_fused = weight * scale[:, None]
    b_fused = bn_b - bn_mean * scale
    self.linear = nn.Linear(in_c, out_c, bias=True)
    with torch.no_grad():
      self.linear.weight.copy_(torch.from_numpy(w_fused.astype(np.float32)))
      self.linear.bias.copy_(torch.from_numpy(b_fused.astype(np.float32)))

  def forward(self, flat_feats: torch.Tensor) -> torch.Tensor:
    return F.relu(self.linear(flat_feats))


class PillarAttentionNet(nn.Module):
  """Matches host ``_pillar_attention`` (GELU FFN, residual LayerNorms)."""

  def __init__(self, weights: dict[str, np.ndarray], dim: int = 32):
    super().__init__()
    self.dim = dim
    self.in_proj = nn.Linear(dim, 3 * dim, bias=True)
    self.out_proj = nn.Linear(dim, dim, bias=True)
    self.norm1 = nn.LayerNorm(dim, eps=1e-5)
    self.ffn0 = nn.Linear(dim, dim, bias=True)
    self.ffn2 = nn.Linear(dim, dim, bias=True)
    self.norm2 = nn.LayerNorm(dim, eps=1e-5)
    with torch.no_grad():
      self.in_proj.weight.copy_(torch.from_numpy(weights["backbone_3d.attn.in_proj_weight"]))
      self.in_proj.bias.copy_(torch.from_numpy(weights["backbone_3d.attn.in_proj_bias"]))
      self.out_proj.weight.copy_(torch.from_numpy(weights["backbone_3d.attn.out_proj.weight"]))
      self.out_proj.bias.copy_(torch.from_numpy(weights["backbone_3d.attn.out_proj.bias"]))
      self.norm1.weight.copy_(torch.from_numpy(weights["backbone_3d.norm1.weight"]))
      self.norm1.bias.copy_(torch.from_numpy(weights["backbone_3d.norm1.bias"]))
      self.ffn0.weight.copy_(torch.from_numpy(weights["backbone_3d.ffn.0.weight"]))
      self.ffn0.bias.copy_(torch.from_numpy(weights["backbone_3d.ffn.0.bias"]))
      self.ffn2.weight.copy_(torch.from_numpy(weights["backbone_3d.ffn.2.weight"]))
      self.ffn2.bias.copy_(torch.from_numpy(weights["backbone_3d.ffn.2.bias"]))
      self.norm2.weight.copy_(torch.from_numpy(weights["backbone_3d.norm2.weight"]))
      self.norm2.bias.copy_(torch.from_numpy(weights["backbone_3d.norm2.bias"]))

  def forward(self, x: torch.Tensor) -> torch.Tensor:
    # x: (1, N, 32)
    residual = x
    qkv = self.in_proj(x)
    q, k, v = qkv.chunk(3, dim=-1)
    scale = 1.0 / math.sqrt(self.dim)
    attn = torch.softmax(torch.matmul(q, k.transpose(-2, -1)) * scale, dim=-1)
    y = torch.matmul(attn, v)
    y = self.out_proj(y)
    y = self.norm1(residual + y)
    h = self.ffn0(y)
    # Match host radarpillars_infer GELU (tanh approx) for tight parity
    h = 0.5 * h * (1.0 + torch.tanh(math.sqrt(2.0 / math.pi) * (h + 0.044715 * h * h * h)))
    h = self.ffn2(h)
    return self.norm2(y + h)


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument(
    "--weights", type=Path,
    default=Path(__file__).resolve().parent / "model_installer/FP16_ft2/radarpillars_preproc_weights.npz",
  )
  ap.add_argument(
    "-o", "--output", type=Path,
    default=Path(__file__).resolve().parent / "model_installer/FP16_ft2",
  )
  ap.add_argument("--example-pillars", type=int, default=128,
                  help="Example N for attention conversion")
  ap.add_argument("--example-points", type=int, default=4096,
                  help="Example M=V*P for VFE conversion")
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  import openvino as ov

  packs = dict(np.load(args.weights))
  out = args.output
  out.mkdir(parents=True, exist_ok=True)

  vfe = VfeLinear(
    packs["vfe.pfn_layers.0.linear.weight"],
    packs["vfe.pfn_layers.0.norm.weight"],
    packs["vfe.pfn_layers.0.norm.bias"],
    packs["vfe.pfn_layers.0.norm.running_mean"],
    packs["vfe.pfn_layers.0.norm.running_var"],
  ).eval()
  attn = PillarAttentionNet(packs).eval()

  # Dynamic M for VFE
  ex_vfe = torch.zeros(args.example_points, 15)
  with torch.no_grad():
    _ = vfe(ex_vfe)
  ov_vfe = ov.convert_model(
    vfe, example_input=ex_vfe,
    input=[ov.PartialShape([-1, 15])],
  )
  vfe_xml = out / "radarpillars_vfe_linear.xml"
  ov.save_model(ov_vfe, str(vfe_xml), compress_to_fp16=False)
  print("Wrote", vfe_xml)

  # Dynamic N for attention — batch=1, N variable
  ex_attn = torch.zeros(1, args.example_pillars, 32)
  with torch.no_grad():
    _ = attn(ex_attn)
  ov_attn = ov.convert_model(
    attn, example_input=ex_attn,
    input=[ov.PartialShape([1, -1, 32])],
  )
  attn_xml = out / "radarpillars_attention.xml"
  ov.save_model(ov_attn, str(attn_xml), compress_to_fp16=False)
  print("Wrote", attn_xml)

  # Patch config if present
  cfg_path = out / "radarpillars_ov_config.json"
  if cfg_path.is_file():
    cfg = json.loads(cfg_path.read_text())
    cfg["vfe_linear_model"] = vfe_xml.name
    cfg["attention_model"] = attn_xml.name
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("Updated", cfg_path)
  else:
    print("WARN: no config at", cfg_path, file=sys.stderr)

  # Quick numeric check vs numpy path
  rng = np.random.default_rng(0)
  flat = rng.normal(size=(64, 15)).astype(np.float32)
  w = packs["vfe.pfn_layers.0.linear.weight"]
  gamma = packs["vfe.pfn_layers.0.norm.weight"]
  beta = packs["vfe.pfn_layers.0.norm.bias"]
  mean = packs["vfe.pfn_layers.0.norm.running_mean"]
  var = packs["vfe.pfn_layers.0.norm.running_var"]
  ref = flat @ w.T
  ref = (ref - mean) / np.sqrt(var + 1e-3)
  ref = np.maximum(ref * gamma + beta, 0)
  core = ov.Core()
  compiled = core.compile_model(str(vfe_xml), "CPU")
  got = np.array(compiled([flat])[0])
  err = float(np.max(np.abs(got - ref)))
  print(f"VFE parity max|err|={err:.3e}")
  if err > 1e-5:
    raise SystemExit(f"VFE parity failed: {err}")

  x = rng.normal(size=(1, 32, 32)).astype(np.float32)
  compiled_a = core.compile_model(str(attn_xml), "CPU")
  got_a = np.array(compiled_a([x])[0])
  # Host reference via torch
  with torch.no_grad():
    ref_a = attn(torch.from_numpy(x)).numpy()
  err_a = float(np.max(np.abs(got_a - ref_a)))
  print(f"Attention parity max|err|={err_a:.3e}")
  if err_a > 1e-4:
    raise SystemExit(f"Attention parity failed: {err_a}")
  print("Stage 2b export OK")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
