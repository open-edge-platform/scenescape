#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

@pytest.fixture
def params(request, scenescape_env):
  params = {}
  params['user'] = request.config.getoption('--user')
  params['password'] = request.config.getoption('--password')
  params['hours'] = request.config.getoption('--hours')
  params['weburl'] = request.config.getoption('--weburl')
  params['auth'] = request.config.getoption('--auth')
  params['rootcert'] = request.config.getoption('--rootcert')
  params['broker_url'] = request.config.getoption('--broker_url')
  params['broker_port'] = request.config.getoption('--broker_port')
  if params['user'] is None or params['password'] is None or params['hours'] is None:
    pytest.skip()
  return params
