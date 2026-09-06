# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional helpers for asserting MQTT event payload shape."""


def check_event_contains_data(event, event_type):
  """Check that a region/tripwire MQTT event has required keys and types.

  @param    event        Region or tripwire event dict from MQTT.
  @param    event_type   ``"region"`` or ``"tripwire"``.
  """
  event_id = "tripwire_id"
  event_name = "tripwire_name"

  if event_type == 'region':
    event_id = "region_id"
    event_name = "region_name"

  event_data = [
    "timestamp", "scene_id", "scene_name", event_id, event_name, "counts", "objects",
  ]
  event_keys = list(event.keys())
  assert set(event_data) <= set(event_keys)
  print("Message contains required data.")

  for key in event_data:
    if key in ["timestamp", "scene_name", event_id, event_name]:
      assert isinstance(event[key], str)
      assert event[key] != ""
    if key == "scene_id":
      assert isinstance(event[key], str)
    if key == "counts":
      assert isinstance(event[key], dict)
      assert list(event[key].keys()) != []
    if key == "objects":
      assert isinstance(event[key], list)
      assert all(isinstance(obj, dict) for obj in event[key])
  print("Message data matches format.")
  return


def assert_event_objects_have_visibility(event, require_non_empty=False):
  """Assert each object snapshot in an event carries a visibility list.

  Covers Analytics FOV fill / producer pass-through on event payloads.
  Optional relative to :func:`check_event_contains_data` so suites that omit
  visibility stay unchanged.
  """
  for key in ("objects", "entered"):
    for obj in event.get(key, []) or []:
      assert "visibility" in obj, f"Event {key} object missing visibility: {obj}"
      assert isinstance(obj["visibility"], list), (
        f"Event {key} visibility must be a list, got {type(obj['visibility'])}")
      if require_non_empty:
        assert obj["visibility"], f"Event {key} visibility unexpectedly empty: {obj}"
  for exited in event.get("exited", []) or []:
    obj = exited.get("object", exited)
    assert "visibility" in obj, f"Event exited object missing visibility: {obj}"
    assert isinstance(obj["visibility"], list)
