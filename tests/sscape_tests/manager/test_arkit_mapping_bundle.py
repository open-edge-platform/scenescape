# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ARKit mapping-bundle zip validation (no RTAB-Map)."""

import io
import json
import zipfile

import pytest
from django.core.exceptions import ValidationError

from manager.validators import validate_arkit_mapping_bundle_zip, validate_mapping_bundle_zip


def _zip_bytes(members: dict[str, bytes]) -> io.BytesIO:
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w") as zf:
    for name, data in members.items():
      zf.writestr(name, data)
  buf.seek(0)
  buf.name = "bundle.zip"
  return buf


def test_arkit_bundle_accepts_worldmap_and_manifest():
  payload = _zip_bytes({
    "manifest.json": json.dumps({"slam_backend": "arkit", "version": 1}).encode(),
    "arworldmap.bin": b"bplist00fake-world-map",
    "baseline_meta.json": b"{}",
  })
  assert validate_arkit_mapping_bundle_zip(payload) is payload


def test_arkit_bundle_rejects_rtabmap_db():
  payload = _zip_bytes({
    "manifest.json": json.dumps({"slam_backend": "arkit"}).encode(),
    "arworldmap.bin": b"bplist00x",
    "rtabmap.db": b"not-a-real-db",
  })
  with pytest.raises(ValidationError, match="rtabmap.db"):
    validate_arkit_mapping_bundle_zip(payload)


def test_arkit_bundle_rejects_wrong_backend():
  payload = _zip_bytes({
    "manifest.json": json.dumps({"slam_backend": "rtabmap"}).encode(),
    "arworldmap.bin": b"bplist00x",
  })
  with pytest.raises(ValidationError, match="slam_backend"):
    validate_arkit_mapping_bundle_zip(payload)


def test_rtab_validator_still_requires_rtabmap_db():
  payload = _zip_bytes({
    "manifest.json": json.dumps({"slam_backend": "arkit"}).encode(),
    "arworldmap.bin": b"bplist00x",
  })
  with pytest.raises(ValidationError, match="rtabmap.db"):
    validate_mapping_bundle_zip(payload)
