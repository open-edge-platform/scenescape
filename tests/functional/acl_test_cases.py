# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.
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
