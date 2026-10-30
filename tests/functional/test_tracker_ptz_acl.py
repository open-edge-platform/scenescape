#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Broker ACL decisions for the Tracker's PTZ pose and status subscriptions.

The Tracker subscribes only to poses of the PTZ cameras of its Manager-loaded scenes
that the deployment assigns to a Resolver, and to those Resolvers' status topics. The
broker ACL is Manager's authoritative decision (the aclcheck endpoint) for the identity
the Tracker deployment is provisioned with: pose reads follow Cam.scene membership, and
that identity can never publish poses or status.
"""

import json
from http import HTTPStatus
from pathlib import Path

import pytest
import requests
import yaml

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

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKER_COMPOSE_FILES = (
  REPO_ROOT / "tests" / "compose" / "compose.tracker.yml",
  REPO_ROOT / "sample_data" / "compose" / "compose.dl-streamer-example.yml",
)
SCENE_CAMERA_ID = "acl-tracker-ptz-scene"
ORPHAN_CAMERA_ID = "acl-tracker-ptz-orphan"
RESOLVER_ID = "positioning-default"


def _tracker_identity_file(compose_path):
  """Basename of the auth file the Tracker service is provisioned with."""
  compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
  tracker = compose["services"]["tracker"]
  env = dict(item.split("=", 1) for item in tracker["environment"])
  auth_path = env["TRACKER_MANAGER_AUTH_PATH"]
  for secret in tracker["secrets"]:
    if secret["target"] == auth_path:
      return Path(compose["secrets"][secret["source"]]["file"]).name
  raise AssertionError(f"{compose_path}: no secret mounted at {auth_path}")


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


@pytest.mark.test_name("NEX-T#####")
def test_tracker_deployments_use_the_identity_checked_here(params, result_recorder):
  """Every Tracker deployment is provisioned with the identity these ACL tests check."""
  for compose_path in TRACKER_COMPOSE_FILES:
    assert _tracker_identity_file(compose_path) == Path(params["auth"]).name, compose_path
  result_recorder.success()


@pytest.mark.test_name("NEX-T#####")
def test_tracker_may_read_poses_only_of_cameras_in_a_scene(rest, params, cameras,
                                                           result_recorder):
  """Pose reads are allowed for a scene camera, denied for unknown and scene-less cameras."""
  for access in (READ_ONLY, CAN_SUBSCRIBE):
    allowed = _acl(rest, params, _pose_topic(SCENE_CAMERA_ID), access)
    assert allowed.status_code == HTTPStatus.OK, allowed.text
    for camera_id in ("acl-tracker-ptz-unknown", ORPHAN_CAMERA_ID):
      denied = _acl(rest, params, _pose_topic(camera_id), access)
      assert denied.status_code == HTTPStatus.FORBIDDEN, (camera_id, denied.text)
      assert denied.json()["result"] == "deny"
  result_recorder.success()


@pytest.mark.test_name("NEX-T#####")
def test_tracker_cannot_publish_poses_or_status(rest, params, cameras, result_recorder):
  """The Tracker consumes poses and status; its identity can never publish them."""
  assert _acl(rest, params, _pose_topic(SCENE_CAMERA_ID), WRITE_ONLY).status_code \
    == HTTPStatus.FORBIDDEN
  status_topic = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=RESOLVER_ID)
  assert _acl(rest, params, status_topic, READ_ONLY).status_code == HTTPStatus.OK
  assert _acl(rest, params, status_topic, WRITE_ONLY).status_code == HTTPStatus.FORBIDDEN
  result_recorder.success()
