#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""FuncTestSpec and auth constants for end-to-end test orchestration."""

from dataclasses import dataclass

AUTH_CONTROLLER = "controller.auth"
AUTH_BROWSER = "browser.auth"

@dataclass
class FuncTestSpec:
  """Specification for a single functional/UI test."""
  profile: object  # ServiceProfile
  auth: str = ""
  require_password: bool = True
  test_name: str = ""
  extra_args: list = None

  def __post_init__(self):
    if self.extra_args is None:
      self.extra_args = []
