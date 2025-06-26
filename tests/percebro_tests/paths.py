#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader
import sys

def init():
  test_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
  root_dir_path = os.path.dirname(test_dir_path)
  percebro_path = os.path.join(os.path.join(root_dir_path, 'percebro'), 'percebro')
  spec = spec_from_loader("percebro", SourceFileLoader("percebro", percebro_path))
  percebro = module_from_spec(spec)
  spec.loader.exec_module(percebro)
  return percebro
