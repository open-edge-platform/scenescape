#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from tests.ui import UserInterfaceTest

TEST_NAME = "NEX-T10494"
MEDIA_PATH = "media/HazardZoneSceneLarge.png"

class WillOurShipGo(UserInterfaceTest):
  def navigateAndCheck(self, path=MEDIA_PATH):
    """! Navigate to the specified path and check that is was reached"""
    self.browser.get(f"{self.params['weburl']}/{path}")
    text = "401 Unauthorized"
    print(self.browser.page_source)
    return not (text in self.browser.page_source)

  def checkForMalfunctions(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      print("\nChecking media access when unauthenticated")
      assert not self.navigateAndCheck()

      print("Checking media/ access after login")
      assert self.login()
      assert self.navigateAndCheck()

      print("Checking media/ access after logout")
      self.browser.get(f"{self.params['weburl']}/sign_out")
      assert not self.navigateAndCheck()

      self.exitCode = 0
    finally:
      self.browser.close()
      self.recordTestResult()
    return

def test_restricted_media_access(request, record_xml_attribute):
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return

def main():
  return test_restricted_media_access(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
