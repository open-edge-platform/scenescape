# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import threading
from types import SimpleNamespace

from manager.api import CameraManager
from scene_common.mqtt import PubSub


def _lockIsFreeForOtherThread(condition):
  """Condition uses an RLock, so only another thread can detect a leaked lock."""
  result = []

  def attempt():
    acquired = condition.acquire(timeout=0.5)
    if acquired:
      condition.release()
    result.append(acquired)

  thread = threading.Thread(target=attempt)
  thread.start()
  thread.join()
  return result[0]


def test_malformed_image_reply_releases_condition():
  manager = CameraManager.__new__(CameraManager)
  manager.imageCondition = threading.Condition()

  wrapped = PubSub.__new__(PubSub).wrapCallback(manager.imageReceived)
  wrapped(None, None, SimpleNamespace(topic='t', payload=b'{not json'))

  assert _lockIsFreeForOtherThread(manager.imageCondition)
