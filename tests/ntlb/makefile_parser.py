# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import subprocess
import re
from test_result import TestResult

BROKEN_TARGETS = ["broken-features", "broken-tests", "randomly-failing-tests"]

class MakefileParser:
  TARGET_PATTERN = r"^([0-9a-z_][-a-z0-9_]*):"

  def __init__(self, directory):
    self.directory = directory

    cmd = ["make", "-qp", "-C", self.directory, "tests", "release-tests"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    self.lines = result.stdout.splitlines()

    self.findAllTargets()
    self.makefiles = {self.allTargets[x].makefile for x in self.allTargets}
    self.findZephyrTestIDs()

    return

  def findAllTargets(self):
    self.allTargets = {}
    tgPattern = self.TARGET_PATTERN + r"$"
    mfPattern = r"# *recipe to execute \(from '([^']+)', line ([0-9]+)\):"
    clPattern = self.TARGET_PATTERN + " *(.+)"
    skipNext = False
    target = None
    self.collections = {}
    for row in self.lines:
      doSkip = skipNext
      skipNext = False
      if doSkip or ":=" in row:
        continue

      if row == "# Not a target:":
        skipNext = True
        continue

      if not len(row):
        continue

      m = re.match(tgPattern, row)
      if m:
        target = m.group(1)
        self.allTargets[target] = TestResult(target, TestResult.SKIPPED)

      m = re.match(mfPattern, row)
      if m and target:
        result = self.allTargets[target]
        result.makefile = m.group(1)
        result.line = int(m.group(2))

      m = re.match(clPattern, row)
      if m:
        name = m.group(1)
        self.collections[name] = m.group(2).split()

    for coll in self.collections:
      if coll[0] == '_':
        d = self.allTargets.pop(coll[1:], None)
      for target in self.allTargets:
        if target in self.collections[coll]:
          self.allTargets[target].addCollection(coll)

    reports = [x for x in self.allTargets if self.allTargets[x].makefile == "Makefile.reports"]
    for target in reports:
      self.allTargets.pop(target, None)

    return

  def findZephyrTestIDs(self):
    pattern = self.TARGET_PATTERN + r" *# *(NEX-T[0-9]+)"
    for makefile in self.makefiles:
      targetLines = [self.allTargets[x].line - 2 for x in self.allTargets
               if self.allTargets[x].makefile == makefile]
      targetLines.sort()
      path = os.path.join(self.directory, makefile)
      with open(path) as f:
        idx = 0
        while True:
          line = f.readline()
          if not line:
            break

          if idx in targetLines:
            m = re.match(pattern, line)
            if m:
              target = m.group(1)
              zephyrTestID = m.group(2)
              self.allTargets[target].zephyrTestID = zephyrTestID

          idx += 1

    return

  def getCommitIDs(self, commitID=None):
    path = os.path.join(self.directory, "Makefile")
    cmd = ["git", "log", "--pretty=format:%h"]
    if commitID:
      cmd.append(commitID)
    cmd.append(path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.splitlines()

  @staticmethod
  def getDependencies(target, path):
    dependencies = set()
    cmd = ["sed", "-e", r":a;N;$!ba;s/\\\n/ /g", path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = result.stdout.splitlines()
    pattern = r"^" + target
    for row in lines:
      if re.match(pattern, row):
        deps = row.split()
        dependencies.update(deps[1:])
    return dependencies

  @staticmethod
  def brokenTests(path):
    broken = set()
    for target in BROKEN_TARGETS:
      broken.update(MakefileParser.getDependencies(target + ":", path))
    return broken
