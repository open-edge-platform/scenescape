#!/usr/bin/env python3

# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

from tests.functional import FunctionalTest
from scene_common.rest_client import RESTClient
from scene_common import log
import time
import os
import requests
from tests.functional.acl_test_cases import test_cases
import json

TEST_NAME = "SAIL-T479"
MAX_CONTROLLER_WAIT = 30
BASE_URL = "https://web.scenescape.intel.com/api/v1/aclcheck"
TOKEN_LIST_URL = "https://web.scenescape.intel.com/api/v1/token-list"
BROWSER_AUTH = '/run/secrets/browser.auth'

class ACLCheck(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])
    return

  def runACLCheck(self):
    try:
      time.sleep(MAX_CONTROLLER_WAIT)
      for user in test_cases.keys():
        self.exit_code = 1
        for test in test_cases[user]:
          payload = {
          "username": user,
          "topic": test["topic"],
          "acc": test["acc"],
          }
          log.log("sending acl check for {} with request {}".format(user, payload))
          response = requests.post(BASE_URL, json=payload, headers = {'Authorization': 'Token ' + self.rest.token}, verify=False)
          actual_result = json.loads(response.text)
          assert actual_result == test['expected_result']
      self.exit_code = 0
    finally:
      self.recordTestResult()
    return

def test_acl_check(request, record_xml_attribute):
  test = ACLCheck(TEST_NAME, request, record_xml_attribute)
  test.runACLCheck()
  assert test.exit_code == 0
  return test.exit_code

def main():
  return test_acl_check(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
