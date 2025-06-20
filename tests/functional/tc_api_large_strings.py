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
import os
import random
import string

TEST_NAME = 'NEX-T10583'

class APIStrings(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.sceneID = None
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    assert res, (res.errors)
    return

  def generate_string(self, length=256):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for _ in range(length))

  def runApiStrings(self):
    self.exitCode = 1
    self.getScene()
    random_string = self.generate_string()
    res = self.rest.authenticate(self.params['user'], random_string)
    print(res.errors['password'])
    assert res.errors['password'] == ['Ensure this field has no more than 150 characters.']
    res = self.rest.authenticate(random_string, self.params['user'])
    print(res.errors['username'])
    assert res.errors['username'] == ['Ensure this field has no more than 150 characters.']
    res = self.rest.authenticate('admin123', 'admin123')
    print(res.errors['non_field_errors'])
    assert res.errors['non_field_errors'] == ['Incorrect Username/Password. ']
    assert res.statusCode == 400
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    res = self.rest.createTripwire({"name": random_string, "scene": self.sceneID})
    print(res.errors['name'])
    assert res.errors['name'] == ['Ensure this field has no more than 200 characters.']
    res = self.rest.createRegion({"name": random_string, "scene": self.sceneID})
    print(res.errors['name'])
    assert res.errors['name'] == ['Ensure this field has no more than 200 characters.']
    res = self.rest.createSensor({"name": random_string, "scene": self.sceneID})
    print(res.errors['name'])
    assert res.errors['name'] == ['Ensure this field has no more than 200 characters.']
    res = self.rest.createCamera({"name": random_string, "scene": self.sceneID})
    print(res.errors['name'])
    assert res.errors['name'] == ['Ensure this field has no more than 200 characters.']
    res = self.rest.createScene({"name": random_string})
    print(res.errors['name'])
    assert res.errors['name'] == ['Ensure this field has no more than 200 characters.']
    res = self.rest.createSensor({"sensor_id": random_string, "scene": self.sceneID})
    print(res.errors['sensor_id'])
    assert res.errors['sensor_id'] == ['Ensure this field has no more than 20 characters.']
    self.exitCode = 0
    self.recordTestResult()
    return

def test_api_strings(request, record_xml_attribute):
  test = APIStrings(TEST_NAME, request, record_xml_attribute)
  test.runApiStrings()
  assert test.exitCode == 0
  return

def main():
  return test_api_strings(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
