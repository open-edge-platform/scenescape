#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

import pytest

from tests.ui.common_markerless import POLYCAM_ZIP_DEFAULT, POLYCAM_ZIP_ENV


@pytest.fixture
def polycam_zip(repo_root):
  """! Path of the Polycam dataset; POLYCAM_ZIP_PATH overrides the copy in test_media."""
  path = os.environ.get(POLYCAM_ZIP_ENV) or os.path.join(repo_root, POLYCAM_ZIP_DEFAULT)
  if not os.path.isfile(path):
    pytest.skip(f"Polycam dataset not found; set {POLYCAM_ZIP_ENV} to its path")
  return path

