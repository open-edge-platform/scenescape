#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

def pytest_addoption(parser):
  parser.addoption('--url', action='store', help='RSTP stream URL to use in test')
  return
