#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Remote ID → external_source adapter pure helpers."""

import importlib.util
import io
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scene_common.schema import SchemaValidation

# Adapter imports remoteid at module load; keep unit tests free of that dep.
sys.modules.setdefault("remoteid", MagicMock())

_REPO = Path(__file__).resolve().parents[2]
_ADAPTER_PATH = _REPO / "tools" / "external_source_adapters" / "remoteid_to_external_source.py"
_SPEC = importlib.util.spec_from_file_location("remoteid_to_external_source", _ADAPTER_PATH)
_ADAPTER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ADAPTER)

RemoteIdPublisher = _ADAPTER.RemoteIdPublisher
build_payload = _ADAPTER.build_payload
read_pcap = _ADAPTER.read_pcap
source_id_for = _ADAPTER.source_id_for

SCHEMA_PATH = _REPO / "controller" / "src" / "schema" / "metadata.schema.json"


def _verdict(**overrides):
  fields = {
    "verdict": "spoofed", "score": 0.0, "reasons": ["known_spoofer", "teleport"],
    "address": "AE:99:6E:B0:EE:1F", "uas_id": "1581F5FJD239C00DW22E",
    "latitude": 47.3716198, "longitude": 8.5292706, "altitude_m": 215.0,
  }
  fields.update(overrides)
  return SimpleNamespace(**fields)


class _FakeTracker:
  """Returns queued verdicts; frames that are not Remote ID raise ValueError."""

  def __init__(self, verdicts):
    self.verdicts = list(verdicts)

  def ingest(self, frame, transport, now_ms=None):
    if frame == b"not-rid":
      raise ValueError("not recognised as Remote ID")
    return self.verdicts.pop(0)


def test_source_id_is_topic_safe_and_stable():
  assert source_id_for("rid-", "AE:99:6E:B0:EE:1F") == "rid-ae996eb0ee1f"
  assert source_id_for("rid-", "ae-99-6e-b0-ee-1f") == "rid-ae996eb0ee1f"
  assert source_id_for("rid-", "+#/ab") == "rid-ab"


def test_payload_is_wgs84_pose_with_trust_metadata():
  payload = build_payload(_verdict(), "rid-ae996eb0ee1f", "vehicle")
  assert payload["source_id"] == "rid-ae996eb0ee1f"
  assert payload["pose"]["reference_frame"] == "wgs84"
  assert payload["pose"]["lat_long_alt"] == [47.3716198, 8.5292706, 215.0]
  (obj,) = payload["objects"]
  assert obj["id"] == "rid-ae996eb0ee1f"
  assert obj["translation"] == [0.0, 0.0, 0.0]
  assert obj["metadata"]["remote_id_trust"] == {
    "label": "spoofed", "confidence": 0.0, "model_name": "remoteid"}
  assert obj["metadata"]["remote_id_reasons"]["label"] == ["known_spoofer", "teleport"]
  assert obj["metadata"]["remote_id_uas_id"]["label"] == "1581F5FJD239C00DW22E"


@pytest.mark.parametrize("check_format", [False, True])
@pytest.mark.parametrize("uas_id", ["1581F5FJD239C00DW22E", None])
def test_payload_validates_against_external_source_schema(check_format, uas_id):
  schema = SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)
  payload = build_payload(_verdict(uas_id=uas_id), "rid-ae996eb0ee1f", "vehicle")
  assert schema.validateMessage("external_source", payload, check_format)


@pytest.mark.parametrize("missing", ["latitude", "longitude", "altitude_m"])
def test_no_payload_without_geodetic_position(missing):
  assert build_payload(_verdict(**{missing: None}), "rid-x", "vehicle") is None


def test_publisher_skips_non_rid_frames_and_rate_limits_per_transmitter():
  other = _verdict(address="02:00:00:00:00:01", verdict="plausible", score=0.5)
  tracker = _FakeTracker([_verdict(), _verdict(), other, _verdict()])
  publisher = RemoteIdPublisher(tracker, "rid-", "vehicle", None, interval_ms=1000)

  assert publisher.ingest(0, "radiotap", b"not-rid") is None
  first = publisher.ingest(0, "radiotap", b"f1")
  assert first[0] == "rid-ae996eb0ee1f"
  assert publisher.ingest(500, "radiotap", b"f2") is None  # same aircraft, too soon
  second = publisher.ingest(600, "radiotap", b"f3")         # another aircraft is due
  assert second[0] == "rid-020000000001"
  assert second[1]["objects"][0]["metadata"]["remote_id_trust"]["label"] == "plausible"
  assert publisher.ingest(1000, "radiotap", b"f4")[0] == "rid-ae996eb0ee1f"


def test_publisher_waits_for_position():
  tracker = _FakeTracker([_verdict(latitude=None), _verdict()])
  publisher = RemoteIdPublisher(tracker, "rid-", "vehicle", None, interval_ms=1000)
  assert publisher.ingest(0, "radiotap", b"basic-id-only") is None
  assert publisher.ingest(100, "radiotap", b"location") is not None


@pytest.mark.parametrize("endian,magic,unit_per_ms", [
  ("<", 0xA1B2C3D4, 1000),
  (">", 0xA1B2C3D4, 1000),
  ("<", 0xA1B23C4D, 1000000),
])
def test_read_pcap_yields_frames_with_millisecond_times(endian, magic, unit_per_ms):
  frames = [b"\x00\x00\x08\x00\x00\x00\x00\x00beacon", b"second"]
  data = struct.pack(endian + "IHHiIII", magic, 2, 4, 0, 0, 65535, 127)
  for i, frame in enumerate(frames):
    data += struct.pack(endian + "IIII", 100 + i, 250 * unit_per_ms, len(frame), len(frame))
    data += frame
  out = list(read_pcap(io.BytesIO(data)))
  assert out == [(100250, "radiotap", frames[0]), (101250, "radiotap", frames[1])]


def test_read_pcap_rejects_other_link_types():
  data = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)  # Ethernet
  with pytest.raises(SystemExit):
    list(read_pcap(io.BytesIO(data)))
