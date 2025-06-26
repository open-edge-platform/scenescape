# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from enum import Enum, auto

class _TestStatus(Enum):
  FAILED = auto()
  EXECUTED = auto()
  SKIPPED = auto()

class TestResult:
  # Suites seem to be code_check, infra, metric, perf, smoke, stability, system, ui, unit
  SUITE_REMAP = {
    'sscape': "unit",
  }
  MAKEFILE_IGNORE = ["percebro-unit"]

  def __init__(self, target, status):
    if target is None:
      raise ValueError("No target")
    self.target = target
    self.status = status
    self.zephyrTestID = None
    self.makefile = None
    self.line = None
    return

  def addCollection(self, name):
    if not hasattr(self, 'collections'):
      self.collections = []
    if name[0] == '_':
      name = name[1:]
    self.collections.append(name)
    return

  @property
  def suite(self):
    suite = None

    if hasattr(self, 'collections'):
      suite = self.collections[0]
      suffix = "-tests"
      if suite.endswith(suffix):
        suite = suite[:-len(suffix)]

    # Prefer Makefile name for suite if it is available
    if self.target not in self.MAKEFILE_IGNORE \
       and hasattr(self, 'makefile') and '.' in self.makefile:
      base, ext = os.path.splitext(os.path.basename(self.makefile))
      if base == "Makefile":
        suite = ext[1:]
      elif ext in (".make", ".mk"):
        suite = base

    if suite in self.SUITE_REMAP:
      suite = self.SUITE_REMAP[suite]

    return suite

  @property
  def name(self):
    if not hasattr(self, 'zephyrTestID'):
      return "unknown"
    return f"{self.zephyrTestID}"

  @property
  def reportPath(self):
    directory = ""
    if self.suite == "unit":
      directory = os.path.join(directory, "unit-tests")
    path = os.path.join(directory, self.target + ".xml")
    return path

  # FIXME - find a way to parse self.output and find "stacktrace", "assert message", "stderr"

# Really gross way to put _TestStatus constants directly into TestResult class
for key in _TestStatus:
  setattr(TestResult, key.name, key)
