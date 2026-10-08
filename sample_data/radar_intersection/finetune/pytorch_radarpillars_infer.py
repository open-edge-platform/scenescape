#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PyTorch RadarPillars single-cloud inference (OpenPCDet / RadarPillar ckpt).

Requires a RadarPillar checkout (``RADARPILLAR_ROOT`` or sibling ``../RadarPillar``)
with venv + editable install. Example::

  export RADARPILLAR_ROOT=/path/to/RadarPillar
  \"$RADARPILLAR_ROOT\"/.venv/bin/python pytorch_radarpillars_infer.py \\
    --ckpt \"$RADARPILLAR_ROOT\"/weights/radarpillar_vod_best_map52.56.pth \\
    --bin /path/to/frame.bin --score-threshold 0.03
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from radarpillar_env import ensure_radarpillar_on_sys_path  # noqa: E402

_RP = ensure_radarpillar_on_sys_path()

from pcdet.config import cfg, cfg_from_yaml_file  # noqa: E402
from pcdet.datasets import DatasetTemplate  # noqa: E402
from pcdet.models import build_network, load_data_to_gpu  # noqa: E402
from pcdet.utils import common_utils  # noqa: E402

# PyTorch 2.6+ defaults weights_only=True; OpenPCDet ckpts need full unpickle.
_torch_load = torch.load


def _torch_load_compat(*args, **kwargs):
  kwargs.setdefault("weights_only", False)
  return _torch_load(*args, **kwargs)


torch.load = _torch_load_compat


class SingleCloudDataset(DatasetTemplate):
  """One-shot dataset wrapping an in-memory (N,7) float32 cloud."""

  def __init__(self, dataset_cfg, class_names, points: np.ndarray, logger=None):
    super().__init__(
      dataset_cfg=dataset_cfg, class_names=class_names, training=False,
      root_path=None, logger=logger)
    self._points = np.asarray(points, dtype=np.float32).reshape(-1, points.shape[-1])

  def __len__(self):
    return 1

  def __getitem__(self, index):
    return self.prepare_data(data_dict={
      "points": self._points.copy(),
      "frame_id": 0,
    })


class RadarPillarsTorch:
  def __init__(self, cfg_file: Path, ckpt: Path, device: str = "cuda:0"):
    self._rp_root = _RP
    prev = Path.cwd()
    os.chdir(self._rp_root)
    try:
      cfg_from_yaml_file(str(Path(cfg_file).resolve()), cfg)
      self.class_names = list(cfg.CLASS_NAMES)
      self.logger = common_utils.create_logger()
      dummy = np.zeros((1, 7), np.float32)
      dummy[0, 0] = 1.0
      ds = SingleCloudDataset(cfg.DATA_CONFIG, self.class_names, dummy, self.logger)
      self.model = build_network(
        model_cfg=cfg.MODEL, num_class=len(self.class_names), dataset=ds)
      self.model.load_params_from_file(
        filename=str(Path(ckpt).resolve()), logger=self.logger, to_cpu=True)
      self.cfg = cfg
    finally:
      os.chdir(prev)
    self.device = torch.device(device if torch.cuda.is_available() else "cpu")
    self.model.to(self.device)
    self.model.eval()

  def infer(self, points: np.ndarray, score_threshold: float = 0.1) -> list[dict]:
    points = np.asarray(points, dtype=np.float32)
    if points.size == 0:
      return []
    if points.ndim != 2 or points.shape[1] < 7:
      raise ValueError(f"expected (N,7+) points, got {points.shape}")
    points = points[:, :7]
    # OpenPCDet voxelize drops out-of-range points; empty pillar coords crash
    # PillarAttention — treat as no detections (common on sparse VIDETEC).
    pc = np.asarray(self.cfg.DATA_CONFIG.POINT_CLOUD_RANGE, dtype=np.float32)
    if pc.size >= 6:
      m = (
        (points[:, 0] >= pc[0]) & (points[:, 0] < pc[3])
        & (points[:, 1] >= pc[1]) & (points[:, 1] < pc[4])
        & (points[:, 2] >= pc[2]) & (points[:, 2] < pc[5]))
      if int(m.sum()) == 0:
        return []
    prev = Path.cwd()
    os.chdir(self._rp_root)
    try:
      ds = SingleCloudDataset(
        self.cfg.DATA_CONFIG, self.class_names, points, self.logger)
      data_dict = ds.collate_batch([ds[0]])
      voxels = data_dict.get("voxels")
      if voxels is None or (hasattr(voxels, "shape") and voxels.shape[0] == 0):
        return []
      load_data_to_gpu(data_dict)
      if self.device.type == "cpu":
        for k, v in list(data_dict.items()):
          if torch.is_tensor(v):
            data_dict[k] = v.cpu()
      try:
        with torch.no_grad():
          pred_dicts, _ = self.model.forward(data_dict)
      except (RuntimeError, IndexError) as exc:
        # Sparse / near-empty pillar batches crash PillarAttention in OpenPCDet.
        self.logger.warning("RadarPillarsTorch skip empty/sparse forward: %s", exc)
        return []
    finally:
      os.chdir(prev)
    pred = pred_dicts[0]
    boxes = pred["pred_boxes"].detach().cpu().numpy()
    scores = pred["pred_scores"].detach().cpu().numpy()
    labels = pred["pred_labels"].detach().cpu().numpy()
    out = []
    for i, (box, score, lab) in enumerate(zip(boxes, scores, labels)):
      if float(score) < score_threshold:
        continue
      cls_idx = int(lab) - 1
      cat = self.class_names[cls_idx] if 0 <= cls_idx < len(self.class_names) else "unknown"
      out.append({
        "id": i + 1,
        "category": cat.lower() if cat != "Car" else "vehicle",
        "confidence": float(score),
        "translation": [float(box[0]), float(box[1]), float(box[2])],
        "size": [float(box[3]), float(box[4]), float(box[5])],
        "yaw": float(box[6]),
      })
    return out


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--cfg-file", type=Path,
                  default=_RP / "tools/cfgs/vod_models/vod_radarpillar_rot.yaml")
  ap.add_argument("--ckpt", type=Path,
                  default=_RP / "weights/radarpillar_vod_best_map52.56.pth")
  ap.add_argument("--bin", type=Path, required=True)
  ap.add_argument("--score-threshold", type=float, default=0.03)
  ap.add_argument("--device", default="cuda:0")
  ap.add_argument("-o", "--output", type=Path, default=None)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  points = np.fromfile(args.bin, dtype=np.float32).reshape(-1, 7)
  model = RadarPillarsTorch(args.cfg_file, args.ckpt, device=args.device)
  objs = model.infer(points, score_threshold=args.score_threshold)
  text = json.dumps({"path": str(args.bin), "n_points": int(points.shape[0]),
                     "objects": objs}, indent=2) + "\n"
  if args.output:
    args.output.write_text(text)
  print(text)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
