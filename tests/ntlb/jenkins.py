# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from junit import JUnit
from test_result import TestResult

class ReportUpdater:
  def __init__(self, directory, overwrite=True):
    self.directory = directory
    self.overwrite = overwrite
    return

  def update(self, allTests, broken=None, ignoreSkipped=False):
    statusLines = []
    for test in allTests:
      result = allTests[test]
      path = self.expandPath(result)
      report = JUnit(path)

      if result.status == TestResult.FAILED:
        report.stdoutText = result.output

      if result.status in (TestResult.FAILED, TestResult.EXECUTED):
        statusLines.append(self.statusLine(result, report))

      if (result.status != report.status \
          or test != report.classname \
          or result.suite != report.suite \
          or result.name != report.name) \
         and (not ignoreSkipped or result.status != TestResult.SKIPPED):
        report.status = result.status
        report.suite = result.suite
        report.name = result.name
        report.classname = test

        if result.status == TestResult.SKIPPED and broken and test in broken:
          report.skippedText = "marked as broken"

        if report.modified:
          if not self.overwrite:
            base, ext = os.path.splitext(report.path)
            report.save(base + "-modified" + ext)
          else:
            report.save()

    statusLines.sort(key=lambda x:x[0])
    self.printResults(statusLines)
    return

  def expandPath(self, result):
    return os.path.join(self.directory, result.reportPath)

  def statusLine(self, result, report):
    path = self.expandPath(result)
    status = self.statusString(result)
    prevStatus = ""
    if result.status != report.status and os.path.exists(path):
      prevStatus = f"WAS: {self.statusString(report)}"

    suite = f"SUITE: {result.suite}/{report.suite}"

    return (status, result.target, result.zephyrTestID, suite, prevStatus)

  def statusString(self, test):
    status = "PASS"
    if test.status == TestResult.FAILED:
      status = "FAIL"
    elif test.status == TestResult.SKIPPED:
      status = "SKIPPED"
    return status

  def printResults(self, statusLines):
    columnWidth = [0] * len(statusLines[0])

    for row in statusLines:
      for idx, col in enumerate(row):
        cw = len(str(col))
        if cw > columnWidth[idx]:
          columnWidth[idx] = cw

    for row in statusLines:
      for idx, col in enumerate(row):
        print(f"{str(col):{columnWidth[idx]}}  ", end="")
      print()

    return
