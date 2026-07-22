# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from scene_common.schema import SchemaValidation
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "controller" / "src" / "schema" / "metadata.schema.json"
INVALID_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "controller" / "src" / "schema" / "invalid.metadata.schema.json"

@pytest.fixture
def schemaObject():
  schemaObj = SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)
  return schemaObj

@pytest.fixture
def objData3D():
  timestamp = "1970-01-01T00:00:00.000Z"

  jdata = {"id": "camera1",
          "objects": {},
          "timestamp": timestamp,
          "rate": 9.8}

  obj = {"id": 1,
        "category": "person",
        "confidence": 1,
        "translation": [0.5, 1.0, -0.23],
        "rotation": [0.43, -0.52, 0.12, 0.21],
        "size": [1.0, 2.0, 0.5]}
  jdata['objects']['person'] = [obj]
  return jdata

@pytest.fixture
def objData():
  timestamp = "1970-01-01T00:00:00.000Z"
  point = { "x": 0.56, "y": 0.0, "width": 0.24, "height": 0.49}

  jdata = {"id": "camera1",
          "objects": {},
          "timestamp": timestamp,
          "rate": 9.8}

  obj = {"id": 1,
        "category": "person",
        "confidence": 1,
        "bounding_box": point,
        "bounding_box_px": point}
  jdata['objects']['person'] = [obj]
  return jdata

@pytest.fixture
def singletonData():
  timestamp = "1970-01-01T00:00:00.000Z"
  jdata = {"id": "temp1",
          "timestamp": timestamp,
          "value": 95.8}

  return jdata

@pytest.fixture
def emptyObjData(objData):
  objData = {}
  return objData

@pytest.fixture
def externalSourceData():
  timestamp = "1970-01-01T00:00:00.000Z"
  jdata = {
    "timestamp": timestamp,
    "source_id": "drone-1",
    "pose": {
      "reference_frame": "wgs84",
      "lat_long_alt": [37.4, -122.1, 10.0],
      "rotation": [0, 0, 0, 1],
    },
    "objects": [
      {"id": "obj-1", "category": "vehicle", "translation": [1.0, 2.0, 0.0]},
    ],
  }
  return jdata

