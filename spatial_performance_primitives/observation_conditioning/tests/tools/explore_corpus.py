#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Print, per scenario, how many objects raise each decision flag (corpus tuning aid)."""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")

import numpy as np  # noqa: E402

from observation_conditioning import AmodalReasoner  # noqa: E402
from oc_corpus.capture import capture_decisions  # noqa: E402
from oc_corpus.scenarios import FLAGS, build_corpus  # noqa: E402


def main():
  only = sys.argv[1:]
  for name, scenario in build_corpus().items():
    if only and name not in only:
      continue
    dec = capture_decisions(scenario, AmodalReasoner)
    flags = dec["dec/flags"]
    counts = {flag: int(np.count_nonzero(flags & bit)) for flag, bit in FLAGS.items()}
    missing = [flag for flag in scenario.expect if not counts[flag]]
    print(f"{name:24s} N={len(flags):4d} " + " ".join(f"{k[:8]}={v}" for k, v in counts.items())
          + (f"  MISSING {missing}" if missing else ""))


if __name__ == "__main__":
  main()
