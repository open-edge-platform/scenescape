#!/usr/bin/env python3

# Copyright (C) 2022-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
