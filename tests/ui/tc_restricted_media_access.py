#!/usr/bin/env python3

# Copyright (C) 2023-2024 Intel Corporation
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
  return test.exitCode

def main():
  return test_restricted_media_access(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
