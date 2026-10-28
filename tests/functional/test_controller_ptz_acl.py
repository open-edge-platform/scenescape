#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Broker ACL decisions for the Scene Controller's PTZ pose and status subscriptions.

The ACL is Manager's authoritative decision (the broker's aclcheck endpoint): pose reads
follow Cam.scene membership, so a camera that is unknown or not part of any scene cannot
be subscribed to, and the Controller identity can never publish poses.
"""

import json
from http import HTTPStatus

import pytest
import requests

from scene_common.mqtt import PubSub
from scene_common.options import CAN_SUBSCRIBE, READ_ONLY, WRITE_ONLY
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

SCENE_CAMERA_ID = "acl-ptz-scene"
ORPHAN_CAMERA_ID = "acl-ptz-orphan"
RESOLVER_ID = "positioning-default"


def _acl(rest, params, topic, access):
  user = json.load(open(params["auth"], encoding="utf-8"))["user"]
  return requests.post(
    f"{params['resturl']}/aclcheck",
    headers={"Authorization": f"Token {rest.token}"},
    json={"username": user, "topic": topic, "acc": access},
    verify=params["rootcert"],
  )


def _pose_topic(camera_id):
  return PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=camera_id)


@pytest.fixture
def cameras(rest, scene_uid):
  created = rest.createCamera({"name": SCENE_CAMERA_ID, "sensor_id": SCENE_CAMERA_ID,
                               "scene": scene_uid})
  assert created, (created.statusCode, created.errors)
  orphan = rest.createCamera({"name": ORPHAN_CAMERA_ID, "sensor_id": ORPHAN_CAMERA_ID})
  assert orphan, (orphan.statusCode, orphan.errors)
  yield
  for camera_id in (SCENE_CAMERA_ID, ORPHAN_CAMERA_ID):
    rest.deleteCamera(camera_id)


@pytest.mark.test_name("NEX-T29972")
def test_controller_may_read_poses_of_cameras_in_a_scene(rest, params, cameras, result_recorder):
  """Pose reads are allowed for a camera that belongs to a scene."""
  for access in (READ_ONLY, CAN_SUBSCRIBE):
    response = _acl(rest, params, _pose_topic(SCENE_CAMERA_ID), access)
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json()["result"] == "allow"
  result_recorder.success()


@pytest.mark.test_name("NEX-T29973")
def test_controller_cannot_read_poses_of_unknown_or_scene_less_cameras(
    rest, params, cameras, result_recorder):
  """Pose reads are denied for an unknown camera and for a camera outside every scene."""
  for camera_id in ("acl-ptz-unknown", ORPHAN_CAMERA_ID):
    for access in (READ_ONLY, CAN_SUBSCRIBE):
      response = _acl(rest, params, _pose_topic(camera_id), access)
      assert response.status_code == HTTPStatus.FORBIDDEN, (camera_id, response.text)
      assert response.json()["result"] == "deny"
  result_recorder.success()


@pytest.mark.test_name("NEX-T29974")
def test_controller_cannot_publish_poses_and_may_read_resolver_status(
    rest, params, cameras, result_recorder):
  """The Controller consumes poses and status; it can never publish them."""
  write = _acl(rest, params, _pose_topic(SCENE_CAMERA_ID), WRITE_ONLY)
  assert write.status_code == HTTPStatus.FORBIDDEN, write.text
  status_topic = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=RESOLVER_ID)
  assert _acl(rest, params, status_topic, READ_ONLY).status_code == HTTPStatus.OK
  assert _acl(rest, params, status_topic, WRITE_ONLY).status_code == HTTPStatus.FORBIDDEN
  result_recorder.success()
