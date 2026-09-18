# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
import json
from types import SimpleNamespace

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "controller" / "src" / "schema" / "metadata.schema.json"
INVALID_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "controller" / "src" / "schema" / "invalid.metadata.schema.json"

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

@pytest.mark.parametrize("data, expected, format", [("externalSourceData", True, False),
                                            ("externalSourceData", False, False),
                                            ("externalSourceData", True, True),
                                            ("emptyObjData", False, True)])
def test_validateExternalSourceMessage(schemaObject, data, expected, format, request):
  externalSourceData = request.getfixturevalue(data)
  if externalSourceData and expected == False:
    del externalSourceData['source_id']

  result = schemaObject.validateMessage("external_source", externalSourceData, format)
  assert result == expected
  return

def test_validateExternalSourceMessage_missingLatLongAltForWgs84(schemaObject, externalSourceData):
  """A wgs84 pose without lat_long_alt must fail validation."""
  del externalSourceData['pose']['lat_long_alt']

  result = schemaObject.validateMessage("external_source", externalSourceData, True)
  assert result == False
  return

def test_validateExternalSourceMessage_scenePoseRequiresTranslation(schemaObject, externalSourceData):
  """A scene-frame pose without translation must fail validation."""
  externalSourceData['pose'] = {
    "reference_frame": "scene",
    "rotation": [0, 0, 0, 1],
  }

  result = schemaObject.validateMessage("external_source", externalSourceData, True)
  assert result == False
  return

def test_validateExternalSourceMessage_scenePoseWithTranslation(schemaObject, externalSourceData):
  """A scene-frame pose with translation is valid; rotation is optional."""
  externalSourceData['pose'] = {
    "reference_frame": "scene",
    "translation": [1.0, 2.0, 3.0],
  }

  result = schemaObject.validateMessage("external_source", externalSourceData, True)
  assert result == True
  return

def test_validateExternalSourceMessage_noPoseWithEmptyObjects(schemaObject):
  """A message with no pose and no objects (cache reuse / pose-only update) is valid."""
  jdata = {
    "timestamp": "1970-01-01T00:00:00.000Z",
    "source_id": "drone-1",
    "objects": [],
  }

  result = schemaObject.validateMessage("external_source", jdata, True)
  assert result == True
  return

def test_validateExternalSourceMessage_objectWithoutSizeIsValid(schemaObject):
  """A point observation with no size is valid (unlike camera detections)."""
  jdata = {
    "timestamp": "1970-01-01T00:00:00.000Z",
    "source_id": "drone-1",
    "objects": [
      {"id": "obj-1", "category": "person", "translation": [1.0, 2.0, 0.0]},
    ],
  }

  result = schemaObject.validateMessage("external_source", jdata, True)
  assert result == True
  return

@pytest.mark.parametrize("track", [None, True])
def test_validateExternalSourceMessage_trackedObjectWithoutIdIsValid(schemaObject, track):
  """Tracked observations may omit source-local ids."""
  jdata = {
    "timestamp": "1970-01-01T00:00:00.000Z",
    "source_id": "drone-1",
    "objects": [
      {"category": "person", "translation": [1.0, 2.0, 0.0]},
    ],
  }
  if track is not None:
    jdata["track"] = track

  result = schemaObject.validateMessage("external_source", jdata, True)
  assert result == True
  return

def test_validateExternalSourceMessage_untrackedObjectWithoutIdIsInvalid(schemaObject):
  """Untracked observations require a source-local id to preserve."""
  jdata = {
    "timestamp": "1970-01-01T00:00:00.000Z",
    "source_id": "drone-1",
    "track": False,
    "objects": [
      {"category": "person", "translation": [1.0, 2.0, 0.0]},
    ],
  }

  result = schemaObject.validateMessage("external_source", jdata, True)
  assert result == False
  return

def test_validateExternalSourceMessage_pixelDetectionWithoutTranslationIsValid(schemaObject):
  """Pixel external detections may omit translation when pose and intrinsics are present."""
  jdata = {
    "timestamp": "1970-01-01T00:00:00.000Z",
    "source_id": "drone-1",
    "pose": {
      "reference_frame": "wgs84",
      "lat_long_alt": [37.4, -122.1, 10.0],
    },
    "intrinsics": {
      "fx": 905.0,
      "fy": 905.0,
      "cx": 640.0,
      "cy": 360.0,
    },
    "objects": [
      {
        "category": "person",
        "bounding_box_px": {
          "x": 221,
          "y": 157,
          "width": 108,
          "height": 259,
        },
      },
    ],
  }

  result = schemaObject.validateMessage("external_source", jdata, True)
  assert result == True
  return

def test_validateExternalSourceMessage_pixelDetectionRequiresIntrinsics(schemaObject):
  jdata = {
    "timestamp": "1970-01-01T00:00:00.000Z",
    "source_id": "drone-1",
    "pose": {
      "reference_frame": "wgs84",
      "lat_long_alt": [37.4, -122.1, 10.0],
    },
    "objects": [
      {
        "category": "person",
        "bounding_box_px": {
          "x": 221,
          "y": 157,
          "width": 108,
          "height": 259,
        },
      },
    ],
  }

  result = schemaObject.validateMessage("external_source", jdata, True)
  assert result == False
  return

def test_validateExternalSourceMessage_pixelDetectionRejectsTopLeftShape(schemaObject):
  jdata = {
    "timestamp": "1970-01-01T00:00:00.000Z",
    "source_id": "drone-1",
    "pose": {
      "reference_frame": "wgs84",
      "lat_long_alt": [37.4, -122.1, 10.0],
    },
    "intrinsics": {
      "fx": 905.0,
      "fy": 905.0,
      "cx": 640.0,
      "cy": 360.0,
    },
    "objects": [
      {
        "category": "person",
        "bounding_box_px": {
          "top": 157,
          "left": 221,
          "width": 108,
          "height": 259,
        },
      },
    ],
  }

  result = schemaObject.validateMessage("external_source", jdata, True)
  assert result == False
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
