#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from tests.ui import UserInterfaceTest
from selenium.common.exceptions import WebDriverException
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
import pytest

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

TEST_NAME = "NEX-T10494"
MEDIA_PATH = "media/HazardZoneSceneLarge.png"

class WillOurShipGo(UserInterfaceTest):
  def navigateAndCheck(self, path=MEDIA_PATH, expect_unauthorized=False):
    url = f"{self.params['weburl']}/{path}"
    print(f"Navigating to: {url}")

    try:
      self.browser.set_page_load_timeout(30)
      self.browser.get(url)
      text = "401 Unauthorized"
      got_unauthorized = text in self.browser.page_source

      if expect_unauthorized:
        print(f"Expected: 401 Unauthorized | Got: {'401 Unauthorized' if got_unauthorized else 'Accessible'}")
        return not got_unauthorized  # return False if unauthorized found (expected)
      else:
        print(f"Expected: Accessible | Got: {'Accessible' if not got_unauthorized else '401 Unauthorized'}")
        return not got_unauthorized
    except (WebDriverException, Exception) as e:
      print(f"Navigation failed: {e}")
      if expect_unauthorized:
        return False
      return False

  def checkForMalfunctions(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      print("Checking media access when unauthenticated")
      assert not self.navigateAndCheck(expect_unauthorized=True)

      print("\nChecking media access after login")
      assert self.login()
      assert self.navigateAndCheck(expect_unauthorized=False)

      print("\nChecking media access after logout")
      self.browser.get(f"{self.params['weburl']}/sign_out")
      assert not self.navigateAndCheck(expect_unauthorized=True)

      self.exitCode = 0
    finally:
      try:
        self.browser.close()
      except WebDriverException:
        pass
      self.recordTestResult()
    return

@pytest.mark.test_name("NEX-T10494")
def test_restricted_media_access(scenescape_env, request, record_xml_attribute):
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return

def main():
  return test_restricted_media_access(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
