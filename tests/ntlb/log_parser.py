# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import re
from test_result import TestResult

class LogParser:
  MAKE_LINE_PREFIX = r"Makefile.*:[0-9]+: "
  MAKE_CMD_PREFIX = r"^make(\[[0-9]+])?: "
  RE_TARGET = MAKE_LINE_PREFIX + r"target '([0-9a-z][-0-9a-z_]+)' does not exist"
  RE_OUTPUT_END = MAKE_CMD_PREFIX + "Leaving directory"
  RE_OUTPUT_BEGIN = MAKE_CMD_PREFIX + "Entering directory"
  RE_FAILED = MAKE_CMD_PREFIX + r"\*\*\* \[" + MAKE_LINE_PREFIX + r"([^]]+)]"
  RE_NOTREMADE = MAKE_CMD_PREFIX + r"Target '([0-9a-z_][-0-9a-z+]+)' not remade"

  def __init__(self, logfile):
    with open(logfile) as f:
      self.logLines = f.read().splitlines()
    return

  def updateTests(self, allTargets=None):
    self.findAllTests(allTargets)
    self.findFailedTests()
    return

  def findAllTests(self, allTargets=None):
    self.allTests = {}
    if allTargets is None:
      allTargets = {}

    test = None
    output = []
    unknownOutput = []
    for idx, row in enumerate(self.logLines):
      skip = False
      for pattern in \
          (self.RE_TARGET, self.RE_OUTPUT_END, self.RE_OUTPUT_BEGIN,
           self.RE_FAILED, self.RE_NOTREMADE):
        if re.match(pattern, row):
          if test:
            self.allTests[test].output = "\n".join(output)
          elif output:
            unknownOutput.append(output)
          output = []
          if pattern != self.RE_TARGET:
            test = None
            skip = True
          break
      if skip:
        continue

      m = re.match(self.RE_TARGET, row)
      if m:
        test = m.group(1)
        result = allTargets.get(test, TestResult(test, TestResult.EXECUTED))
        result.status = TestResult.EXECUTED
        self.allTests[test] = result
      else:
        output.append(row)

    for test in self.allTests:
      if not getattr(self.allTests[test], 'output', None):
        pattern = r"RUNNING.* TEST " + test
        found = False
        for output in unknownOutput:
          for row in output:
            if re.match(pattern, row):
              self.allTests[test].output = "\n".join(output)
              found = True
              break
          if found:
            break

    return

  def findFailedTests(self):
    self.failedTests = []
    for row in self.logLines:
      m = re.match(self.RE_FAILED, row)
      if m:
        test = m.group(2)
        if test in self.allTests:
          self.allTests[test].status = TestResult.FAILED
    return
