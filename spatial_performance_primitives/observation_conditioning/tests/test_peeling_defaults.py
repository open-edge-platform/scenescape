# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""One layer is enough: peeling deeper layers never changes a result (I3)."""

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from observation_conditioning import AmodalReasoner, constants  # noqa: E402
from oc_corpus import baseline  # noqa: E402
from oc_corpus.capture import build_reasoner  # noqa: E402
from oc_corpus.ocb import read_ocb  # noqa: E402

ARRAYS, META = read_ocb(Path(__file__).resolve().parent / "data" / "mvp-original.ocb")


def test_default_is_a_single_layer():
  assert constants.DEFAULT_NUM_LAYERS == 1
  scenario = baseline.load_scenario(ARRAYS, META, "floor_only")
  scenario.num_layers = constants.DEFAULT_NUM_LAYERS
  reasoner = build_reasoner(scenario, AmodalReasoner)
  assert reasoner.depth_map.num_layers == 1
  assert reasoner.depth_map.t_hit_map.shape == (scenario.height, scenario.width)


@pytest.mark.parametrize("name", ["occluder_box", "wall_flipped", "random_fuzz",
                                  "terrain_cam_back_right"])
def test_extra_layers_do_not_change_the_result(name):
  scenario = baseline.load_scenario(ARRAYS, META, name)
  obs = scenario.observations
  results, first_hits = [], []
  for layers in (1, 4):
    scenario.num_layers = layers
    reasoner = build_reasoner(scenario, AmodalReasoner)
    with warnings.catch_warnings():
      warnings.simplefilter("ignore")
      results.append(reasoner.generate({key: value.copy() for key, value in obs.items()}))
    t_hit = reasoner.depth_map.t_hit_map
    first_hits.append(t_hit if layers == 1 else t_hit[..., 0])
  np.testing.assert_array_equal(results[0][0], results[1][0])
  np.testing.assert_array_equal(results[0][1], results[1][1])
  np.testing.assert_array_equal(first_hits[0], first_hits[1])
