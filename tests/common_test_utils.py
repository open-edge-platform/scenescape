#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

def record_test_result(name: str, error: int):
  print(f"\n{name}:", "FAIL" if error else "PASS")
  print("-----------------------------\n")
  return

def check_event_contains_data(event, event_type):
  """! This function checks if the published mqtt event contains the required attributes with the expected datatype.
  @param    event        The tripwire/region mqtt event returned in the form of Python dict.
  @param    event_type   The event type can either region or tripwire
  """
  event_id = "tripwire_id"
  event_name = "tripwire_name"

  if event_type == 'region':
    event_id = "region_id"
    event_name = "region_name"

  event_data = ["timestamp","scene_id","scene_name", event_id, event_name ,"counts","objects"]
  event_keys = list(event.keys())
  # Check if all the data exists in the event message payload
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
