# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene-scoped external platform state, separate from observed-object output."""

import orjson

from controller.external_source import _CachedPose
from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from scene_common.transform import CameraPose


class SourceStatePublisher:
  """Publish retained source snapshots; expiry tombstones clear retained state."""

  def __init__(self, pubsub: PubSub) -> None:
    self.pubsub = pubsub

  def publish(self, scene_uid: str, source_id: str, state: _CachedPose) -> None:
    """Publish resolved state, including pose-only and cached-pose updates."""
    pose = CameraPose(state.pose_mat, None)
    payload = {
      'scene_id': scene_uid,
      'source_id': source_id,
      'timestamp': get_iso_time(state.when),
      'expires_at': get_iso_time(state.expires_at),
      'translation': pose.translation.asNumpyCartesian.tolist(),
      'rotation': pose.quaternion_rotation.tolist(),
    }
    for field in ('intrinsics', 'distortion'):
      value = getattr(state, field)
      if value is not None:
        payload[field] = value
    if state.cameras is not None:
      payload['cameras'] = state.cameras
    log.debug(
      f"Publishing external source state: scene={scene_uid} source={source_id} "
      f"camera_ids={[camera['id'] for camera in state.cameras or []]} "
      f"camera_field_present={'cameras' in payload}")
    self._publish(scene_uid, source_id, orjson.dumps(payload))

  def remove(self, scene_uid: str, source_id: str) -> None:
    """Clear a source's retained snapshot on cache expiry or invalidation."""
    self._publish(scene_uid, source_id, b'')

  def _publish(self, scene_uid: str, source_id: str, payload: bytes) -> None:
    topic = PubSub.formatTopic(
      PubSub.DATA_SOURCE, scene_id=scene_uid, source_id=source_id)
    result = self.pubsub.publish(topic, payload, qos=1, retain=True)
    if result.rc != 0:
      log.error(f"Failed to queue source state: scene={scene_uid} source={source_id} "
                f"mqtt_rc={result.rc}")
