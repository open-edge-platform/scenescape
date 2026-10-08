#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export VIDETEC-trained roadside PointNetSeg → OpenVINO IR (FP16).

Intel-optimized inference path for phase-2 (OpenVINO Runtime). Host keeps
feature normalize + class-aware instance clustering.

Example::

  python3 roadside/export_roadside_ov.py \\
    --ckpt VIDETEC-2/phase1_baselines/roadside_videtec_ccby.pt \\
    -o model_installer/roadside/FP16
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

_HERE = Path(__file__).resolve().parent
_RI_ROOT = _HERE.parent
if str(_RI_ROOT / "baselines") not in sys.path:
  sys.path.insert(0, str(_RI_ROOT / "baselines"))
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from roadside_common import FEATURE_DIM, NUM_CLASSES  # noqa: E402
from roadside_seg import PointNetSeg  # noqa: E402


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--ckpt", type=Path, required=True,
                  help="roadside_videtec_ccby.pt (VIDETEC / CC BY 4.0)")
  ap.add_argument("-o", "--output-dir", type=Path, required=True)
  ap.add_argument("--fp16", action="store_true", default=True)
  ap.add_argument("--no-fp16", action="store_false", dest="fp16")
  ap.add_argument("--example-n", type=int, default=32)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  payload = torch.load(args.ckpt, map_location="cpu", weights_only=False)
  model = PointNetSeg()
  model.load_state_dict(payload["model"])
  model.eval()

  example = torch.randn(args.example_n, FEATURE_DIM, dtype=torch.float32)
  with torch.no_grad():
    ref = model(example).numpy()

  try:
    import openvino as ov
  except ImportError as exc:
    raise SystemExit("openvino required: pip install openvino") from exc

  ov_model = ov.convert_model(model, example_input=example)
  # Dynamic number of points
  ov_model.reshape({ov_model.input(0): [-1, FEATURE_DIM]})

  args.output_dir.mkdir(parents=True, exist_ok=True)
  xml_path = args.output_dir / "roadside_pointnet_seg.xml"
  bin_path = args.output_dir / "roadside_pointnet_seg.bin"
  ov.save_model(ov_model, str(xml_path), compress_to_fp16=bool(args.fp16))

  core = ov.Core()
  compiled = core.compile_model(str(xml_path), "CPU")
  ov_out = compiled([example.numpy()])[compiled.output(0)]
  max_abs = float(np.max(np.abs(ov_out - ref)))
  print(f"parity max|Δlogits| vs torch: {max_abs:.6g}", flush=True)

  config = {
    "model_type": "roadside",
    "nn_model": xml_path.name,
    "input_features": FEATURE_DIM,
    "num_classes": NUM_CLASSES,
    "class_names": ["background", "person", "vehicle"],
    "norm_stats": payload.get("norm_stats"),
    "cluster_distance_m": 2.0,
    "min_score": 0.35,
    "accumulate_half_window_default": 0,
    "precision": "FP16" if args.fp16 else "FP32",
    "train_meta": {
      k: payload.get("meta", {}).get(k)
      for k in (
        "train_data", "train_data_license", "train_data_attribution",
        "labeling", "excludes_datasets", "code_license",
      )
    },
    "source_ckpt": str(args.ckpt.name),
  }
  cfg_path = args.output_dir / "roadside_ov_config.json"
  cfg_path.write_text(json.dumps(config, indent=2) + "\n")
  # Keep norm_stats beside IR for installers that strip train_meta
  (args.output_dir / "norm_stats.json").write_text(
    json.dumps(payload.get("norm_stats") or {}, indent=2) + "\n")

  print(f"wrote {xml_path} + {bin_path} + {cfg_path}", flush=True)
  if max_abs > 0.05:
    print("WARNING: OV vs torch logits differ more than 0.05", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
