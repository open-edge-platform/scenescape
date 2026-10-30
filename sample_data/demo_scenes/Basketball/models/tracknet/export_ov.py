#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Export tracknet_best.pt → OpenVINO FP16."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openvino as ov
import torch

from model import TrackNet


def main():
  here = Path(__file__).resolve().parent
  outdir = here / ".." / "tracknet-basketball"
  ckpt_path = outdir / "tracknet_best.pt"
  if not ckpt_path.is_file():
    print(f"Missing {ckpt_path}", file=sys.stderr)
    return 1
  state = torch.load(ckpt_path, map_location="cpu", weights_only=False)
  print(
    f"ckpt epoch={state['epoch']} hit={state['hit_rate']:.3f} "
    f"size={state['width']}x{state['height']}",
    flush=True,
  )
  model = TrackNet()
  model.load_state_dict(state["model"])
  model.eval()
  h, w = int(state["height"]), int(state["width"])
  onnx_path = outdir / "tracknet_basketball.onnx"
  dummy = torch.zeros(1, 9, h, w)
  try:
    torch.onnx.export(
      model, dummy, str(onnx_path),
      input_names=["frames"], output_names=["heatmap"],
      opset_version=17, dynamo=False,
    )
  except TypeError:
    torch.onnx.export(
      model, dummy, str(onnx_path),
      input_names=["frames"], output_names=["heatmap"],
      opset_version=17,
    )
  print(f"ONNX → {onnx_path}", flush=True)
  ov_model = ov.convert_model(str(onnx_path))
  xml_path = outdir / "tracknet_basketball.xml"
  ov.save_model(ov_model, str(xml_path), compress_to_fp16=True)
  meta = {
    "height": h,
    "width": w,
    "in_channels": 9,
    "label": "basketball",
    "hit_rate": state["hit_rate"],
    "epoch": state["epoch"],
  }
  (outdir / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
  print(f"OpenVINO FP16 → {xml_path}", flush=True)
  return 0


if __name__ == "__main__":
  sys.exit(main())
