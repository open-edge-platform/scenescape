# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import copy
import json
from pathlib import Path

from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation

TEST_NAME = "NEX-T28223"
REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "controller/src/schema/metadata.schema.json"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/ptz_pose_context_v1.json"


def load_pose_context():
  with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
    return json.load(fixture_file)["message"]


def test_pose_context_fixture_validates():
  validator = SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)
  assert validator.validateMessage("pose_context", load_pose_context(), check_format=True)


def test_pose_context_rejects_invalid_motion_and_missing_pose():
  validator = SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)
  invalid_motion = load_pose_context()
  invalid_motion["motion_state"] = "moving"
  assert not validator.validateMessage("pose_context", invalid_motion)

  invalid_pose = load_pose_context()
  del invalid_pose["pose"]
  assert not validator.validateMessage("pose_context", invalid_pose)


def test_invalid_pose_context_requires_reason_and_omits_pose():
  validator = SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)
  invalid_context = load_pose_context()
  invalid_context["valid"] = False
  invalid_context["invalid_reason"] = "sample_stale"
  invalid_context.pop("pose")
  invalid_context.pop("quality")
  assert validator.validateMessage("pose_context", invalid_context)

  invalid_context_with_pose = copy.deepcopy(invalid_context)
  invalid_context_with_pose["pose"] = load_pose_context()["pose"]
  assert not validator.validateMessage("pose_context", invalid_context_with_pose)


def test_ptz_topics_format_and_match():
  expected_topics = {
      "DATA_CAMERA_POSE": ("camera_id", "cam-1", "scenescape/data/camera/pose/cam-1"),
      "CMD_CAMERA_CONFIG": ("camera_id", "cam-1", "scenescape/cmd/camera/config/cam-1"),
      "SYS_POSITIONING_STATUS": (
          "resolver_id", "resolver-1", "scenescape/sys/positioning/status/resolver-1"),
  }
  for template_name, (identifier, value, expected_topic) in expected_topics.items():
    template = PubSub.getTopicByTemplateName(template_name)
    topic = template.substitute(**{identifier: value})
    assert topic == expected_topic
    assert PubSub.match_topic(template.template, topic) == (value,)
