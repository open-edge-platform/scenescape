#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenVINO Runtime inference for roadside PointNetSeg (+ host clustering)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from roadside_common import (
  class_aware_instances,
  frame_to_features,
  instances_to_objects,
  normalize_features,
)


class RoadsideOVInfer:
  """Intel OpenVINO path for phase-2 roadside perception."""

  def __init__(self, config_path: str | Path, device: str = "CPU"):
    import openvino as ov

    self.config_path = Path(config_path)
    self.config = json.loads(self.config_path.read_text())
    xml = self.config_path.parent / self.config["nn_model"]
    if not xml.is_file():
      raise FileNotFoundError(xml)
    self.norm_stats = self.config.get("norm_stats")
    if self.norm_stats is None:
      ns = self.config_path.parent / "norm_stats.json"
      if ns.is_file():
        self.norm_stats = json.loads(ns.read_text())
    self.cluster_distance_m = float(self.config.get("cluster_distance_m", 2.0))
    self.min_score = float(self.config.get("min_score", 0.35))
    self.device = device.strip().upper() or "CPU"
    core = ov.Core()
    self.compiled = core.compile_model(str(xml), self.device)
    self._out = self.compiled.output(0)

  def predict_objects(self, frame: np.ndarray) -> dict[str, list[dict]]:
    xyz, feats = frame_to_features(frame)
    if xyz.shape[0] == 0:
      return {}
    feats_n, _ = normalize_features(feats, self.norm_stats)
    logits = self.compiled([feats_n])[self._out]
    # softmax
    logits = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(logits)
    prob = exp / np.maximum(exp.sum(axis=1, keepdims=True), 1e-9)
    labels = prob.argmax(axis=1)
    scores = prob.max(axis=1)
    instances = class_aware_instances(
      xyz, labels, scores,
      cluster_distance_m=self.cluster_distance_m,
      min_score=self.min_score,
    )
    return instances_to_objects(instances)
