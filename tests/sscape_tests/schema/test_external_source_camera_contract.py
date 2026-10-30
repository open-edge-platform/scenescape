# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Schema coverage for per-camera external-source observations."""

import pytest


@pytest.fixture
def drone_message(externalSourceData):
  """A body observation and one complete camera snapshot."""
  externalSourceData.update({
    "track": False,
    "cameras": [{
      "id": "front",
      "mount": {
        "translation": [0.2, 0.0, -0.1],
        "rotation": [-0.5, 0.5, -0.5, 0.5],
      },
      "intrinsics": {"fx": 905.0, "fy": 910.0, "cx": 600.0, "cy": 350.0},
      "objects": [],
    }],
  })
  return externalSourceData


@pytest.mark.parametrize("check_format", [False, True])
@pytest.mark.parametrize("reference_frame", ["scene", "wgs84"])
@pytest.mark.parametrize("pose_only", [False, True])
def test_accepts_drone_camera_contract(schemaObject, drone_message, check_format,
                                     reference_frame, pose_only):
  if reference_frame == "scene":
    drone_message["pose"] = {
      "reference_frame": "scene",
      "translation": [2.0, 3.0, 10.0],
      "rotation": [0.0, 0.0, 0.0, 1.0],
    }
  if pose_only:
    drone_message["objects"] = []
  assert schemaObject.validateMessage("external_source", drone_message, check_format)


def test_camera_array_supports_multiple_cameras(schemaObject, drone_message):
  drone_message["cameras"].append({
    **drone_message["cameras"][0],
    "id": "rear",
    "objects": [],
  })
  assert schemaObject.validateMessage("external_source", drone_message, True)


@pytest.mark.parametrize("check_format", [False, True])
@pytest.mark.parametrize("track", [False, True, None])
@pytest.mark.parametrize("with_observations", [False, True])
def test_camera_only_message_does_not_require_top_level_objects(
    schemaObject, drone_message, check_format, track, with_observations):
  """Camera observations and camera-only updates need no body observations."""
  del drone_message["objects"]
  if track is None:
    del drone_message["track"]
  else:
    drone_message["track"] = track
  if with_observations:
    drone_message["cameras"][0]["objects"] = [{
      "id": "person-1",
      "category": "person",
      "translation": [1.0, 2.0, 3.0],
    }]
  assert schemaObject.validateMessage("external_source", drone_message, check_format)


@pytest.mark.parametrize("check_format", [False, True])
def test_message_requires_objects_or_cameras(schemaObject, drone_message, check_format):
  """An envelope without either observation collection remains invalid."""
  del drone_message["objects"]
  del drone_message["cameras"]
  assert not schemaObject.validateMessage("external_source", drone_message, check_format)


@pytest.mark.parametrize("check_format", [False, True])
def test_camera_only_message_still_requires_camera_objects(
    schemaObject, drone_message, check_format):
  """Omitting body observations does not relax the camera contract."""
  del drone_message["objects"]
  del drone_message["cameras"][0]["objects"]
  assert not schemaObject.validateMessage("external_source", drone_message, check_format)


def test_rejects_replaced_top_level_camera_mount(schemaObject, drone_message):
  drone_message["camera_mount"] = drone_message["cameras"][0]["mount"]
  assert not schemaObject.validateMessage("external_source", drone_message, True)


@pytest.mark.parametrize("field", ["id", "mount", "intrinsics", "objects"])
def test_camera_requires_complete_configuration_and_observations(
    schemaObject, drone_message, field):
  del drone_message["cameras"][0][field]
  assert not schemaObject.validateMessage("external_source", drone_message, True)


def test_camera_contract_does_not_accept_resolution(schemaObject, drone_message):
  drone_message["cameras"][0]["resolution"] = [1280, 720]
  assert not schemaObject.validateMessage("external_source", drone_message, True)


def test_external_source_does_not_accept_top_level_resolution(
    schemaObject, drone_message):
  drone_message["resolution"] = [1280, 720]
  assert not schemaObject.validateMessage("external_source", drone_message, True)


@pytest.mark.parametrize("mount", [
  None,
  [],
  {},
  {"translation": [0, 0, 0]},
  {"rotation": [0, 0, 0, 1]},
  {"translation": [0, 0], "rotation": [0, 0, 0, 1]},
  {"translation": [0, 0, 0, 0], "rotation": [0, 0, 0, 1]},
  {"translation": ["0", 0, 0], "rotation": [0, 0, 0, 1]},
  {"translation": [0, 0, 0], "rotation": [0, 0, 0]},
  {"translation": [0, 0, 0], "rotation": [0, 0, 0, 0]},
  {"translation": [0, 0, 0], "rotation": [0, 0, 0, 2]},
  {"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]},
])
def test_rejects_invalid_camera_mount(schemaObject, drone_message, mount):
  drone_message["cameras"][0]["mount"] = mount
  assert not schemaObject.validateMessage("external_source", drone_message, True)


def test_mount_does_not_relax_untracked_identity_requirement(schemaObject, drone_message):
  camera_observation = {
    "category": "person",
    "bounding_box_px": {"x": 10, "y": 20, "width": 30, "height": 40},
  }
  drone_message["cameras"][0]["objects"] = [camera_observation]
  assert not schemaObject.validateMessage("external_source", drone_message, True)


def test_mount_allows_pixel_localization(schemaObject, drone_message):
  drone_message["cameras"][0]["objects"] = [{
    "id": "person-1",
    "category": "person",
    "bounding_box_px": {"x": 100, "y": 120, "width": 40, "height": 80},
  }]
  assert schemaObject.validateMessage("external_source", drone_message, True)


def test_camera_observations_allow_camera_local_cartesian_positions(
    schemaObject, drone_message):
  drone_message["cameras"][0]["objects"] = [{
    "id": "person-1",
    "category": "person",
    "translation": [1.0, 2.0, 3.0],
  }]
  assert schemaObject.validateMessage("external_source", drone_message, True)


@pytest.mark.parametrize("check_format", [False, True])
@pytest.mark.parametrize("camera_observation", [False, True])
def test_untracked_observations_require_id_even_with_extra_identity_field(
    schemaObject, drone_message, check_format, camera_observation):
  """An unsupported identity field cannot replace the source-provided id."""
  observation = {
    "global_id": "obsolete-identity",
    "category": "person",
    "translation": [1.0, 2.0, 3.0],
  }
  if camera_observation:
    del drone_message["objects"]
    drone_message["cameras"][0]["objects"] = [observation]
  else:
    drone_message["objects"] = [observation]
  assert not schemaObject.validateMessage("external_source", drone_message, check_format)
  observation["id"] = "person-1"
  assert schemaObject.validateMessage("external_source", drone_message, check_format)
