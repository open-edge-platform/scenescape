#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest

from scene_common.scenescape import SceneLoader

sscape_tests_path = os.path.dirname(os.path.realpath(__file__))
CONFIG_FULLPATH = os.path.join(sscape_tests_path, "config.json")

@pytest.fixture(scope="module")
def manager():
  """! Creates a scenescape class object as a fixture. """

  return SceneLoader(CONFIG_FULLPATH)
