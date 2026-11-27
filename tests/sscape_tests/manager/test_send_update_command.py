# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

from manager.models import sendUpdateCommand
from scene_common.mqtt import PubSub


def test_notification_failure_after_commit_is_logged_not_raised():
  """Negative: an MQTT failure in the post-commit notice is logged; the saved change is not turned into an error."""
  with patch.dict("os.environ", {"BROKER": "broker"}), \
       patch("manager.models.PubSub", side_effect=OSError("mqtt down")), \
       patch("manager.models.log") as log_mock:
    sendUpdateCommand(scene_id="scene-1")

  log_mock.error.assert_called_once()
  assert "mqtt down" in str(log_mock.error.call_args)


def test_notification_success_publishes_database_update():
  """Positive: a healthy notifier still publishes the database update topic."""
  with patch.dict("os.environ", {"BROKER": "broker"}), \
       patch("manager.models.PubSub") as pubsub_mock, \
       patch("manager.models.requests.patch"):
    pubsub_mock.CMD_DATABASE = PubSub.CMD_DATABASE
    sendUpdateCommand(scene_id="scene-1")

  pubsub_mock.formatTopic.assert_any_call(PubSub.CMD_DATABASE)
  pubsub_mock.return_value.publish.assert_any_call(pubsub_mock.formatTopic.return_value, "update", qos=1)
