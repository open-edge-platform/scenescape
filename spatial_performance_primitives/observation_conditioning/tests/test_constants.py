# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""constants.py holds exactly the values the original implementation used."""

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from observation_conditioning import constants  # noqa: E402
from oc_corpus.legacy import load_legacy  # noqa: E402

# (legacy class, method, parameter) -> constant that now supplies the default
LEGACY_DEFAULTS = {
  ("AmodalReasoner", "_create_probe_points", "devs"): "PROBE_DEVS_AT_PREMISE",
  ("AmodalReasoner", "_wall_spectrum", "l_v"): "VERT_BAND_LOW_DEG",
  ("AmodalReasoner", "_wall_spectrum", "num_rays"): "SPECTRUM_SAMPLES",
  ("AmodalReasoner", "_get_occlusion_depth", "eps"): "OCC_SIGMA_FRAC",
  ("AmodalReasoner", "_get_wall_depth", "l_v"): "VERT_BAND_LOW_DEG",
  ("AmodalReasoner", "_get_wall_depth", "u_v"): "VERT_BAND_HIGH_DEG",
  ("AmodalReasoner", "_total_occlusion", "num_rays"): "TOTAL_OCC_SAMPLES",
  ("AmodalReasoner", "_total_occlusion", "occ_frac"): "TOTAL_OCC_FRACTION",
  ("AmodalReasoner", "_total_occlusion", "eps"): "TOTAL_OCC_BLOCK_MARGIN_M",
  ("AmodalReasoner", "_update_depth_gaussian", "k"): "ADAPTIVE_DAMPING_K",
  ("AmodalReasoner", "_update_depth_gaussian", "r_occ"): "OCC_RESIDUAL_R",
  ("AmodalReasoner", "_update_depth_gaussian", "eps"): "WALL_OCCLUDER_MARGIN_M",
  ("DepthMap", "_peel_rays", "eps"): "PEEL_EPS",
}


@pytest.mark.parametrize("key", sorted(LEGACY_DEFAULTS))
def test_constant_equals_the_legacy_default(key):
  owner, method, parameter = key
  default = inspect.signature(getattr(getattr(load_legacy(), owner), method)) \
      .parameters[parameter].default
  assert getattr(constants, LEGACY_DEFAULTS[key]) == default


def test_constants_that_were_inline_literals():
  assert constants.PROBE_DEVS_OVER_PREMISE == 2.1      # generate(): over-premise probes
  assert constants.DEGENERATE_CROSS_TOL == 1e-6        # frame and signed-angle fallbacks
  assert constants.SPECTRUM_MIN_RISE_M == 0.1          # _wall_spectrum rising support


def test_every_constant_is_used_by_the_package():
  source = "".join(path.read_text() for path in
                   (Path(constants.__file__).parent).glob("[ai]*.py"))
  unused = [name for name in vars(constants) if name.isupper() and name not in source]
  assert not unused
