# Copyright (C) 2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import pytest
from conftest import SCHEMA_PATH, INVALID_SCHEMA_PATH
import json
from types import SimpleNamespace

def mockPayload(objData):
  objData = json.dumps(objData).encode("utf-8")
  msg = {"payload": objData}
  msg = SimpleNamespace(**msg)
  return msg

@pytest.mark.parametrize("file, expected", [(SCHEMA_PATH, True),
                                            (INVALID_SCHEMA_PATH, None)])
def test_loadSchema(schemaObject, file, expected):
  schemaObject.mqtt_schema = None
  schemaObject.loadSchema(file)
  if expected:
    assert schemaObject.mqtt_schema
  else:
    assert schemaObject.mqtt_schema == expected
  return

@pytest.mark.parametrize("data, expected, format", [("objData", True, False),
                                            ("objData", False, False),
                                            ("objData", True, True),
                                            ("emptyObjData", False, True)])
def test_validate2DDetectionMessage(schemaObject, data, expected, format, request):
  objData = request.getfixturevalue(data)
  if objData and expected == False:
    del objData['objects']['person'][0]['bounding_box']["x"]

  result = schemaObject.validateMessage("detector", objData, format)
  assert result == expected
  return

@pytest.mark.parametrize("data, expected, format", [("objData3D", True, False),
                                            ("objData3D", False, False),
                                            ("objData3D", True, True)])
def test_validate3DDetectionMessage(schemaObject, data, expected, format, request):
  objData = request.getfixturevalue(data)
  if objData and expected == False:
    del objData['objects']['person'][0]['size']

  result = schemaObject.validateMessage("detector", objData, format)
  assert result == expected
  return

@pytest.mark.parametrize("data, expected, format", [("singletonData", True, False),
                                            ("singletonData", False, False),
                                            ("singletonData", True, True),
                                            ("emptyObjData", False, True)])
def test_validateSingletonMessage(schemaObject, data, expected, format, request):
  singletonData = request.getfixturevalue(data)
  if singletonData and expected == False:
    del singletonData['value']

  result = schemaObject.validateMessage("singleton", singletonData, format)
  assert result == expected
  return

@pytest.mark.parametrize("schemaPath, expected", [(INVALID_SCHEMA_PATH, None),
                                                   (SCHEMA_PATH, True)])
def test_compileValidators(schemaObject, schemaPath, expected):
  schemaObject.validator = {}
  schemaObject.validator_no_format = {}
  schemaObject.mqtt_schema = None
  schemaObject.loadSchema(schemaPath)
  try:
    schemaObject.compileValidators()
  except Exception as e:
    pass

  if expected:
    assert schemaObject.validator
    assert schemaObject.validator_no_format
  else:
    assert not schemaObject.validator
    assert not schemaObject.validator_no_format
  return
