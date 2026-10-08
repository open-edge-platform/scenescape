#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Resolve the external RadarPillar / OpenPCDet checkout (portable).

Fine-tune and PyTorch parity tools need
https://github.com/fthbng77/RadarPillar cloned and installed separately.
Do **not** hard-code developer home paths.

Resolution order:

1. ``RADARPILLAR_ROOT`` environment variable
2. Sibling of the Scenescape repo: ``<scenescape>/../RadarPillar``
3. Optional ``--radarpillar-root`` / caller override

Demo MQTT path uses OpenVINO IRs under ``model_installer/`` only and does
**not** need this checkout. FT2 init weights for further fine-tune live under
``sample_data/radar_intersection/weights/`` (see that folder's README).
"""

from __future__ import annotations

import os
from pathlib import Path

# sample_data/radar_intersection/finetune/ → parents[3] = scenescape root
_FINETUNE_DIR = Path(__file__).resolve().parent
_RI_ROOT = _FINETUNE_DIR.parent
_SCENESCAPE_ROOT = _RI_ROOT.parents[1]

# Shipped FT2 init for further fine-tune (not required for demo OV IR).
FT2_EP11_PTH = _RI_ROOT / "weights" / "radarpillar_videtec_gantry_ft2_ep11.pth"
VOD_BEST_PTH_NAME = "radarpillar_vod_best_map52.56.pth"


def resolve_radarpillar_root(explicit: Path | str | None = None) -> Path:
  """Return RadarPillar root or raise with setup instructions."""
  if explicit is not None:
    root = Path(explicit).expanduser().resolve()
    if root.is_dir():
      return root
    raise FileNotFoundError(f"RADARPILLAR_ROOT override not a directory: {root}")

  env = os.environ.get("RADARPILLAR_ROOT", "").strip()
  if env:
    root = Path(env).expanduser().resolve()
    if root.is_dir():
      return root
    raise FileNotFoundError(
      f"RADARPILLAR_ROOT={env!r} is set but not a directory")

  sibling = (_SCENESCAPE_ROOT.parent / "RadarPillar").resolve()
  if sibling.is_dir():
    return sibling

  raise FileNotFoundError(
    "RadarPillar checkout not found.\n"
    "  export RADARPILLAR_ROOT=/path/to/RadarPillar\n"
    "  # or clone as a sibling of the Scenescape repo:\n"
    "  git clone https://github.com/fthbng77/RadarPillar.git "
    f"{sibling}\n"
    "See sample_data/radar_intersection/finetune/README.md.")


def radarpillar_python(root: Path | None = None) -> Path:
  """Prefer ``$RADARPILLAR_ROOT/.venv/bin/python`` when present."""
  rp = root or resolve_radarpillar_root()
  for rel in (".venv/bin/python", ".venv/Scripts/python.exe"):
    py = rp / rel
    if py.is_file():
      return py
  return Path(os.environ.get("PYTHON", "python3"))


def ensure_radarpillar_on_sys_path(root: Path | None = None) -> Path:
  """Insert RadarPillar (+ tools/) on ``sys.path``; return root."""
  import sys
  rp = root or resolve_radarpillar_root()
  if str(rp) not in sys.path:
    sys.path.insert(0, str(rp))
  tools = rp / "tools"
  if tools.is_dir() and str(tools) not in sys.path:
    sys.path.insert(0, str(tools))
  return rp
