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
import pytest
from pathlib import Path

def pytest_addoption(parser):
  parser.addoption("--user", action="store", help="input useranme", default="admin")
  parser.addoption("--password", action="store", help="input password")
  parser.addoption("--hours", action="store", help="input duration")

@pytest.fixture
def params(request):
  params = {}
  params['user'] = request.config.getoption('--user')
  params['password'] = request.config.getoption('--password')
  params['hours'] = request.config.getoption('--hours')
  params['weburl'] = 'https://web.scenescape.intel.com'
  if params['user'] is None or params['password'] is None or params['hours'] is None:
    pytest.skip()
  return params

@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
  file_name = Path(config.option.file_or_dir[0]).stem
  config.option.htmlpath = os.getcwd() + '/tests/ui/reports/test_reports/' + file_name + ".html"
