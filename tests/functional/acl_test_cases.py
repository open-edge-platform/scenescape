# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common.options import WRITE_ONLY, READ_AND_WRITE

test_cases = {
  "webuser":
  [{
    "topic": "scenescape/event/tripwire/Retail/abc123/objects",
    "acc": str(WRITE_ONLY),
    "expected_result": {"result": "deny"}
  },
  {
    "topic": "scenescape/data/camera/person/camera1",
    "acc": str(WRITE_ONLY),
    "expected_result": {"result": "deny"}
  },
  {
    "topic": "scenescape/data/sensor/camera1",
    "acc": str(WRITE_ONLY),
    "expected_result": {"result": "deny"}
  }],
    "cameras":
  [{
    "topic": "scenescape/autocalibration/camera/pose/camera1",
    "acc": str(READ_AND_WRITE),
    "expected_result": {"result": "deny"}
  },
  {
    "topic": "scenescape/data/sensor/camera1",
    "acc": str(READ_AND_WRITE),
    "expected_result": {"result": "deny"}
  },
  {
    "topic": "scenescape/image/autocalibration/camera/camera1",
    "acc": str(READ_AND_WRITE),
    "expected_result": {"result": "deny"}
  },
  {
    "topic": "scenescape/image/camera/camera1",
    "acc": str(READ_AND_WRITE),
    "expected_result": {"result": "deny"}
  },
  {
    "topic": "scenescape/data/camera/person/camera1",
    "acc": str(READ_AND_WRITE),
    "expected_result": {"result": "deny"}
  },
  {
    "topic": "scenescape/channel/abc123",
    "acc": str(READ_AND_WRITE),
    "expected_result": {"result": "deny"}
  }],
}
