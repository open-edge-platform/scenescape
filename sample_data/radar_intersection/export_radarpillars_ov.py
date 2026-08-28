#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export RadarPillars (HF) BEV backbone + detection head to OpenVINO IR.

Host-side pillar VFE / PillarAttention / scatter stay in Python (numpy) at
runtime; this IR is the OpenVINO-optimized 2-D CNN + 1x1 heads — the same
split used by openvino_contrib PointPillars.

Checkpoint: Fatihbin/radarpillars-vod (Apache-2.0).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


# VoD radar grid (vod_radarpillar_rot.yaml)
PC_RANGE = [0.0, -25.6, -3.0, 51.2, 25.6, 2.0]
VOXEL_SIZE = [0.16, 0.16, 5.0]
BEV_CHANNELS = 32
NX = int(round((PC_RANGE[3] - PC_RANGE[0]) / VOXEL_SIZE[0]))  # 320
NY = int(round((PC_RANGE[4] - PC_RANGE[1]) / VOXEL_SIZE[1]))  # 320


class EasyDict(dict):
  def __getattr__(self, k):
    try:
      return self[k]
    except KeyError as e:
      raise AttributeError(k) from e

  def __setattr__(self, k, v):
    self[k] = v

  def get(self, k, default=None):
    return dict.get(self, k, default)


class BaseBEVBackbone(nn.Module):
  def __init__(self, input_channels=32):
    super().__init__()
    layer_nums = [3, 5, 5]
    layer_strides = [2, 2, 2]
    num_filters = [32, 32, 32]
    upsample_strides = [1, 2, 4]
    num_upsample_filters = [32, 32, 32]
    c_in_list = [input_channels, *num_filters[:-1]]
    self.blocks = nn.ModuleList()
    self.deblocks = nn.ModuleList()
    for idx in range(len(layer_nums)):
      cur = [
        nn.ZeroPad2d(1),
        nn.Conv2d(c_in_list[idx], num_filters[idx], 3,
                  stride=layer_strides[idx], padding=0, bias=False),
        nn.BatchNorm2d(num_filters[idx], eps=1e-3, momentum=0.01),
        nn.ReLU(),
      ]
      for _ in range(layer_nums[idx]):
        cur.extend([
          nn.Conv2d(num_filters[idx], num_filters[idx], 3, padding=1, bias=False),
          nn.BatchNorm2d(num_filters[idx], eps=1e-3, momentum=0.01),
          nn.ReLU(),
        ])
      self.blocks.append(nn.Sequential(*cur))
      self.deblocks.append(nn.Sequential(
        nn.ConvTranspose2d(
          num_filters[idx], num_upsample_filters[idx],
          upsample_strides[idx], stride=upsample_strides[idx], bias=False),
        nn.BatchNorm2d(num_upsample_filters[idx], eps=1e-3, momentum=0.01),
        nn.ReLU(),
      ))
    self.num_bev_features = sum(num_upsample_filters)

  def forward(self, spatial_features):
    ups = []
    x = spatial_features
    for i in range(len(self.blocks)):
      x = self.blocks[i](x)
      ups.append(self.deblocks[i](x))
    return torch.cat(ups, dim=1)


class DetectHeads(nn.Module):
  """1x1 heads: 3 classes × 2 anchors/location = 6 anchors → cls/box/dir."""

  def __init__(self, in_channels=96, num_anchors=6, num_class=3, code_size=7, num_dir_bins=2):
    super().__init__()
    self.conv_cls = nn.Conv2d(in_channels, num_anchors * num_class, 1)
    self.conv_box = nn.Conv2d(in_channels, num_anchors * code_size, 1)
    self.conv_dir_cls = nn.Conv2d(in_channels, num_anchors * num_dir_bins, 1)

  def forward(self, spatial_features_2d):
    return (
      self.conv_cls(spatial_features_2d),
      self.conv_box(spatial_features_2d),
      self.conv_dir_cls(spatial_features_2d),
    )


class RadarPillarsBevDetect(nn.Module):
  def __init__(self):
    super().__init__()
    self.backbone_2d = BaseBEVBackbone(BEV_CHANNELS)
    self.dense_head = DetectHeads(self.backbone_2d.num_bev_features)

  def forward(self, spatial_features):
    feat = self.backbone_2d(spatial_features)
    return self.dense_head(feat)


def load_bev_weights(model: RadarPillarsBevDetect, ckpt_path: Path) -> None:
  raw = torch.load(ckpt_path, map_location="cpu", weights_only=False)
  state = raw["model_state"] if "model_state" in raw else raw
  mapped = {}
  for k, v in state.items():
    if k.startswith("backbone_2d."):
      mapped[k] = v
    elif k.startswith("dense_head.conv_cls"):
      mapped[k.replace("dense_head.", "dense_head.")] = v
    elif k.startswith("dense_head.conv_box"):
      mapped[k] = v
    elif k.startswith("dense_head.conv_dir_cls"):
      mapped[k] = v
  missing, unexpected = model.load_state_dict(mapped, strict=False)
  # Ignore BN num_batches_tracked mismatches etc.
  missing = [m for m in missing if "num_batches_tracked" not in m]
  if missing:
    print("WARN missing keys:", missing[:10], file=sys.stderr)
  if unexpected:
    print("WARN unexpected:", unexpected[:10], file=sys.stderr)


def export_vfe_attn_weights(ckpt_path: Path, out_dir: Path) -> None:
  """Save numpy weight packs for host-side PillarVFE + PillarAttention."""
  raw = torch.load(ckpt_path, map_location="cpu", weights_only=False)
  state = raw["model_state"]
  packs = {}
  for k, v in state.items():
    if k.startswith("vfe.") or k.startswith("backbone_3d."):
      packs[k] = v.detach().cpu().numpy()
  np.savez_compressed(out_dir / "radarpillars_preproc_weights.npz", **packs)
  print("Wrote", out_dir / "radarpillars_preproc_weights.npz")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--ckpt", type=Path, required=True)
  parser.add_argument("-o", "--output", type=Path, required=True,
                      help="Output directory for IR + config")
  args = parser.parse_args()
  out = args.output
  out.mkdir(parents=True, exist_ok=True)

  model = RadarPillarsBevDetect().eval()
  load_bev_weights(model, args.ckpt)
  export_vfe_attn_weights(args.ckpt, out)

  example = torch.zeros(1, BEV_CHANNELS, NY, NX)
  with torch.no_grad():
    cls, box, direction = model(example)
  print("shapes", cls.shape, box.shape, direction.shape)

  import openvino as ov
  ov_model = ov.convert_model(model, example_input=example)
  xml_path = out / "radarpillars_bev_detect.xml"
  ov.save_model(ov_model, str(xml_path))
  print("Wrote", xml_path)

  config = {
    "model": "RadarPillars",
    "source": "Fatihbin/radarpillars-vod",
    "license": "Apache-2.0",
    "point_cloud_range": PC_RANGE,
    "voxel_size": VOXEL_SIZE,
    "max_points_per_voxel": 32,
    "max_voxels": 16000,
    "bev_channels": BEV_CHANNELS,
    "grid_size": [NX, NY, 1],
    "nn_model": str(xml_path.name),
    "preproc_weights": "radarpillars_preproc_weights.npz",
    "score_threshold": 0.1,
    "nms_thresh": 0.1,
    "class_names": ["vehicle", "person", "cyclist"],
    "anchor_sizes": [[3.9, 1.6, 1.56], [0.8, 0.6, 1.73], [1.76, 0.6, 1.73]],
    "anchor_rotations": [0.0, 1.57],
    "anchor_bottom_heights": [-1.78, -0.6, -0.6],
    "feature_map_stride": 2,
    "dir_offset": 0.78539,
    "num_dir_bins": 2,
  }
  (out / "radarpillars_ov_config.json").write_text(json.dumps(config, indent=2) + "\n")
  print("Wrote", out / "radarpillars_ov_config.json")


if __name__ == "__main__":
  main()
