# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from xml.dom import minidom
import codecs
from test_result import TestResult

# https://llg.cubic.org/docs/junit/
# https://github.com/testmoapp/junitxml

VALID_CONTROL = "\b\t\n\f\r"

class JUnit:
  def __init__(self, path):
    self.path = path
    self.modified = False
    if os.path.exists(self.path):
      self.xmldoc = minidom.parse(self.path)
    else:
      self.xmldoc = minidom.parseString(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites>'
        '<testsuite tests="1">'
        '<testcase classname="unknown"></testcase>'
        '</testsuite>'
        '</testsuites>')
    return

  def save(self, path=None):
    if path is None:
      path = self.path
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    with codecs.open(path, "w", "utf-8") as f:
      xml = self.xmldoc.toxml()
      escaped = xml.encode('ascii', 'xmlcharrefreplace').decode('ascii')
      escaped = "".join([c for c in escaped if c >= ' ' or c in VALID_CONTROL])
      f.write(escaped)
    return

  def updateTagAttribute(self, tagName, attribute, value):
    tags = self.xmldoc.getElementsByTagName(tagName)
    for tag in tags:
      tag.setAttribute(attribute, value)
    return len(tags)

  def deleteTag(self, tagName):
    tags = self.xmldoc.getElementsByTagName(tagName)
    for tag in tags:
      parent = tag.parentNode
      parent.removeChild(tag)
    return

  def getText(self, name, attribute):
    message = self.xmldoc.getElementsByTagName(name)
    if not attribute:
      message = message[0] if message else None
    else:
      message = message[0].getAttribute(attribute) if message else None
    return message

  def setText(self, name, attribute, parent, value):
    if self.getText(name, attribute) == value:
      return

    message = self.xmldoc.getElementsByTagName(name)
    if message:
      message = message[0]
    else:
      testcases = self.xmldoc.getElementsByTagName(parent)
      message = self.xmldoc.createElement(name)
      testcases[0].appendChild(message)

    if attribute:
      message.setAttribute(attribute, value)
    else:
      message.appendChild(self.xmldoc.createTextNode(value))
    self.modified = True

  @property
  def status(self):
    if self.errorText is not None:
      return TestResult.FAILED
    skipped = self.xmldoc.getElementsByTagName("skipped")
    if skipped:
      return TestResult.SKIPPED
    return TestResult.EXECUTED

  @status.setter
  def status(self, value):
    if value == self.status:
      return

    count = self.updateTagAttribute("testsuite", "failures",
                                    "1" if value == TestResult.FAILED else "0")
    self.updateTagAttribute("testsuites", "failures",
                            str(count) if value == TestResult.FAILED else "0")
    if value == TestResult.FAILED:
      if self.errorText is None:
        self.errorText = "Test failed"
    else:
      self.deleteTag("failure")

    count = self.updateTagAttribute("testsuite", "skipped",
                                    "1" if value == TestResult.SKIPPED else "0")
    self.updateTagAttribute("testsuites", "skipped",
                            str(count) if value == TestResult.SKIPPED else "0")
    if value == TestResult.SKIPPED:
      skipped = self.xmldoc.getElementsByTagName("skipped")
      if not skipped:
        testcases = self.xmldoc.getElementsByTagName("testcase")
        skipped = self.xmldoc.createElement("skipped")
        testcases[0].appendChild(skipped)
    else:
      self.deleteTag("skipped")

    self.modified = True
    return

  @property
  def suite(self):
    suites = self.xmldoc.getElementsByTagName("testsuite")
    name = suites[0].getAttribute("name")
    return name if name else None

  @suite.setter
  def suite(self, value):
    if value == self.suite:
      return
    suites = self.xmldoc.getElementsByTagName("testsuite")
    suites[0].setAttribute("name", value)
    self.modified = True
    return

  @property
  def name(self):
    testcases = self.xmldoc.getElementsByTagName("testcase")
    name = testcases[0].getAttribute("name")
    return name if name else None

  @name.setter
  def name(self, value):
    if value == self.name:
      return
    testcases = self.xmldoc.getElementsByTagName("testcase")
    testcases[0].setAttribute("name", value)
    self.modified = True
    return

  @property
  def classname(self):
    testcases = self.xmldoc.getElementsByTagName("testcase")
    name = testcases[0].getAttribute("classname")
    return name if name else None

  @name.setter
  def classname(self, value):
    if value == self.classname:
      return
    testcases = self.xmldoc.getElementsByTagName("testcase")
    for testcase in testcases:
      testcase.setAttribute("classname", value)
    self.modified = True
    return

  # Text as message attribute inside <failure> tag becomes "Error" on Tests tab
  #     <failure message="Test Failed"></failure>
  # Text between <failure></failure> becomes "Stacktrace" on Tests tab
  #     <failure>This will be the stacktrace message</failure>
  # Text between <system-out></system-out> will appear in "Standard Output"
  # Text between <system-err></system-err> will appear in "Standard Error"

  @property
  def errorText(self):
    return self.getText("failure", "message")

  @errorText.setter
  def errorText(self, value):
    self.setText("failure", "message", "testcase", value)
    return

  @property
  def stacktraceText(self):
    return self.getText("failure", None)

  @stacktraceText.setter
  def stacktraceText(self, value):
    self.setText("failure", None, "testcase", value)
    return

  @property
  def stdoutText(self):
    return self.getText("system-out", None)

  @stdoutText.setter
  def stdoutText(self, value):
    self.setText("system-out", None, "testcase", value)
    return

  @property
  def stderrText(self):
    return self.getText("system-err", None)

  @stderrText.setter
  def stderrText(self, value):
    self.setText("system-err", None, "testcase", value)
    return

  @property
  def skippedText(self):
    return self.getText("skipped", "message")

  @skippedText.setter
  def skippedText(self, value):
    if self.status != TestResult.SKIPPED:
      raise AttributeError("status is not SKIPPED")
    if value == self.skippedText:
      return

    self.setText("skipped", "message", "testcase", value)
    return
