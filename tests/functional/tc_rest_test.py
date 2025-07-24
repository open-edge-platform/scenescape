#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.functional.rest_test_cases import testCases
import string
import random
import os
import uuid

TEST_NAME = 'NEX-T10464'

class TestAPI(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.sceneID = None
    self.allThings = None
    self.nameField = 'name'
    self.uidField = 'uid'
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])
    return

  def buildArgparser(self):
    parser = FunctionalTest.buildArgparser(self)
    parser.set_defaults(scene='test_scene_1')
    return parser

  def verifyData(self, actualData, expectedData):
    toList = ['points', 'center']
    if 'marker_id' not in actualData:
      actualData.pop('uid')
    actualData.pop('scene', None)
    expectedData.pop('scene', None)
    expectedData.pop('transform_type', None)
    if 'center' in actualData or 'points' in actualData:
      actualData.pop('translation', None)
    expectedData.pop('password', None)  # API should not return password
    if 'username' in expectedData:  # Don't check for name if username exists
      expectedData.pop('name', None)

    expectedKeys = expectedData.keys()
    keysMatched = 0
    for key in expectedKeys:
      if key not in actualData:
        break
      if key == 'rotation' or key == 'scale':
        actualData[key] = [round(val) for val in actualData[key]]
      if key in toList:
        newPoints = []
        for point in actualData[key]:
          if type(point) is list:
            newPoints.append(tuple(point))
          else:
            newPoints.append(point)
        actualData[key] = tuple(newPoints)
      if actualData[key] == expectedData[key]:
        keysMatched += 1
    print('actual: ', actualData)
    print('expected: ', expectedData)
    return keysMatched == len(expectedKeys)

  def getMethod(self, thingName):
    method = None
    try:
      method = getattr(self.rest, thingName)
    except AttributeError:
      raise NotImplementedError('method does not exist')
    return method

  def randomString(self, thingNames):
    randString = None
    while True:
      randString = ''.join(random.choice(string.ascii_letters) \
         for _ in range(random.choice(range(1, 10))))
      if randString not in thingNames:
        break
    return randString

  def prepareScene(self):
    res = self.rest.createScene({'name': self.sceneName})
    assert res, (res.statusCode, res.errors)
    self.sceneID = res['uid']
    assert self.sceneID
    return

  def createThing(self, thing, testCases, scene):
    create = self.getMethod('create{}'.format(thing))
    for test in testCases:
      data = test[0]
      expectedCode = test[1]
      if scene:
        data['scene'] = self.sceneID
      res = create(data)
      if expectedCode == HTTPStatus.CREATED:
        assert res.statusCode == HTTPStatus.CREATED, (res.statusCode, res.errors)
      if expectedCode == HTTPStatus.BAD_REQUEST:
        assert res.statusCode == HTTPStatus.BAD_REQUEST
    return

  def generateUniqueUID(self, thing):
    return str(uuid.uuid4())

  def updateThing(self, thing, testCases, scene):
    create = self.getMethod('create{}'.format(thing))
    update = self.getMethod('update{}'.format(thing))
    for test in testCases:
      uid = None
      data = test[0]
      expectedCode = test[1]
      if expectedCode == HTTPStatus.OK:
        createData = data.copy()
        createData['name'] = 'test_{}'.format(thing)
        if 'sensor_id' in createData:
          createData['sensor_id'] = createData['name']
        elif 'username' in createData:
          createData['username'] = createData['name']
        elif 'marker_id' in createData:
          createData['marker_id'] = createData['name']
        if scene:
          createData['scene'] = self.sceneID
        res = create(createData)
        assert res
        print("CREATED", res)
        uid = res[self.uidField]
      if 'uid' in data:
        uid = self.generateUniqueUID(thing)
      res = update(uid, data)
      assert res.statusCode == expectedCode, (res.statusCode, expectedCode, uid, data)
    return

  def verifyCreate(self, thing, testCases):
    getThings = self.getMethod('get{}s'.format(thing))
    for test in testCases:
      expectedCode = test[1]
      data = test[0]
      if expectedCode == HTTPStatus.CREATED:
        res = getThings({self.nameField: data[self.nameField]})
        if len(res['results']) > 0:
          thing = res['results'][0]
          expectedCode = HTTPStatus.OK
          assert self.verifyData(thing, data)
    return

  def verifyGetAll(self, thing, testCases):
    getThings = self.getMethod('get{}s'.format(thing))
    self.thingNames = []
    self.thingUIDs = []

    for test in testCases:
      expectedCode = test[1]
      nameFilter = test[0]
      if thing == 'CalibrationMarker':
        nameFilter = {'scene': self.sceneID}
      if expectedCode == HTTPStatus.OK:
        res = getThings(nameFilter)
        assert res['results']
        self.allThings = res['results']
    for thing in self.allThings:
      self.thingNames.append(thing[self.nameField])
      self.thingUIDs.append(thing[self.uidField])
    return

  def verifyUpdate(self, thing, testCases):
    getThings = self.getMethod('get{}s'.format(thing))
    for test in testCases:
      expectedCode = test[1]
      data = test[0]
      if expectedCode == HTTPStatus.OK:
        res = getThings({self.nameField: data[self.nameField]})
        if len(res['results']) > 0:
          thing = res['results'][0]
          expectedCode = HTTPStatus.OK
          assert self.verifyData(thing, data)
    return

  def verifyGetDelete(self, thing, method='delete'):
    getDelete = self.getMethod('{}{}'.format(method, thing))
    testCases = [HTTPStatus.OK, HTTPStatus.NOT_FOUND]

    for expectedCode in testCases:
      if expectedCode == HTTPStatus.NOT_FOUND:
        uid = self.generateUniqueUID(thing)
      else:
        uid = self.thingUIDs[0]
      res = getDelete(uid)
      assert res.statusCode == expectedCode, \
        (res.statusCode, expectedCode, thing, uid)

    if method == 'delete':
      uid = self.thingUIDs[0]
      res = getDelete(uid)
      assert res == {}
      assert res.statusCode == HTTPStatus.NOT_FOUND
    return

  def verifyAPI(self, thing, testCases):
    print()
    if thing == 'User':
      self.nameField = 'username'
      self.uidField = 'username'
    if thing == 'CalibrationMarker':
      self.nameField = 'marker_id'
      self.uidField = 'marker_id'
    if self.sceneID is None:
      self.prepareScene()
    print('Running create{} test..'.format(thing))
    self.createThing(thing, testCases['create'], testCases['scene'])
    print('Running update{} test..'.format(thing))
    self.updateThing(thing, testCases['update'], testCases['scene'])
    print()
    print('verifying create{} test..'.format(thing))
    self.verifyCreate(thing, testCases['create'])
    print('verifying update{} test..'.format(thing))
    self.verifyUpdate(thing, testCases['update'])
    print('verifying get{}s test..'.format(thing))
    self.verifyGetAll(thing, testCases['getAll'])
    print('verifying get{} test..'.format(thing))
    self.verifyGetDelete(thing, 'get')
    print('verifying delete{} test..'.format(thing))
    self.verifyGetDelete(thing, 'delete')
    return

  def verifyThings(self):
    try:
      for thing in testCases:
        self.verifyAPI(thing, testCases[thing])
      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

def test_api(request, record_xml_attribute):
  test = TestAPI(TEST_NAME, request, record_xml_attribute)
  test.verifyThings()
  assert test.exitCode == 0
  return

def main():
  return test_api(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
