# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene-data ingestion adapter.

Converts ``scenescape/data/scene/*`` MQTT payloads into analytics-ready
objects with full ``ChainData`` continuity across frames.

This extracts the deserialization and identity-cache logic that previously
lived in ``Scene._deserializeTrackedObjects`` / ``Scene.syncAnalyticsObjects``
so that the analytics package can own it independently of the Controller
internals.
"""

from types import SimpleNamespace
from typing import Dict, List, Optional

from scene_common.geometry import Point, Size
from scene_common.timestamp import get_epoch_time
from scene_common import log

from controller.moving_object import ChainData


class SceneDataIngestion:
  """Convert ``scenescape/data/scene`` MQTT objects into analytics-ready objects.

  Maintains per-object identity (keyed by ``gid``) and location/timestamp
  history so that ``ChainData`` continuity is preserved across MQTT frames.

  Usage::

      ingestion = SceneDataIngestion()
      # On each MQTT message for detection_type "person":
      ingestion.ingest(detection_type, raw_objects, sensors)
      live_objects = ingestion.get_objects(detection_type)

  Both ``_objects`` and ``_history`` are plain mutable dicts.  Scene keeps
  aliased references to them so legacy code paths that access
  ``scene._analytics_objects`` / ``scene.object_history_cache`` continue to
  work without modification.
  """

  def __init__(self):
    # gid → live deserialized SimpleNamespace (identity preserved across frames)
    self._objects: Dict[str, SimpleNamespace] = {}
    # gid → history dict with keys: first_seen, publishedLocations, last_seen
    self._history: Dict[str, dict] = {}

  # ------------------------------------------------------------------
  # Public API
  # ------------------------------------------------------------------

  def ingest(
    self,
    detection_type: str,
    raw_objects: List[dict],
    sensors: Optional[dict],
  ) -> None:
    """Reconcile the object cache for *detection_type* and deserialize.

    Stale entries (objects present in the cache for this type but absent
    from *raw_objects*) are removed.  Each entry in *raw_objects* is built
    or updated in place so ``ChainData`` is preserved.

    Args:
      detection_type: Category string, e.g. ``'person'``.
      raw_objects:    List of MQTT object dicts from the scene-data payload.
      sensors:        Sensor registry dict (``{sensor_id: Sensor}``).  Used
                      to resolve ``singleton_type`` for sensor deserialization.
                      May be ``None`` or empty if no sensors are configured.
    """
    current_ids = {
      obj['id']
      for obj in (raw_objects or [])
      if isinstance(obj, dict) and 'id' in obj
    }

    # Evict objects of this type that are no longer reported
    stale = [
      gid
      for gid, obj in list(self._objects.items())
      if obj.category == detection_type and gid not in current_ids
    ]
    for gid in stale:
      del self._objects[gid]
      self._history.pop(gid, None)

    # Deserialize each raw object, reusing existing entries by id
    for obj_data in (raw_objects or []):
      if not isinstance(obj_data, dict):
        continue
      obj = self._build_one(obj_data, sensors or {})
      self._objects[obj.gid] = obj

  def get_objects(self, detection_type: str) -> List[SimpleNamespace]:
    """Return all live objects for *detection_type*."""
    return [o for o in self._objects.values() if o.category == detection_type]

  def deserialize(
    self,
    serialized_objects,
    sensors: Optional[dict],
  ) -> list:
    """Deserialize *serialized_objects* without reconciliation.

    This replicates the legacy ``Scene._deserializeTrackedObjects`` contract:
    pass-through if already deserialized, then build and index each dict.

    Args:
      serialized_objects: List of dicts **or** already-deserialized objects.
      sensors:            Sensor registry dict.  May be ``None`` or empty.

    Returns:
      List of deserialized objects (may be the original list if the first
      element is not a ``dict``).
    """
    if not serialized_objects or not isinstance(serialized_objects, list):
      return serialized_objects if serialized_objects else []

    if not isinstance(serialized_objects[0], dict):
      return serialized_objects

    result = []
    for obj_data in serialized_objects:
      if not isinstance(obj_data, dict):
        continue
      obj = self._build_one(obj_data, sensors or {})
      self._objects[obj.gid] = obj
      result.append(obj)
    return result

  # ------------------------------------------------------------------
  # Internal helpers
  # ------------------------------------------------------------------

  def _build_one(self, obj_data: dict, sensors: dict) -> SimpleNamespace:
    """Build or update a single live object from an MQTT dict.

    Reuses an existing ``SimpleNamespace`` for the same ``id`` so that
    ``ChainData`` (region history, location history, sensor events) is
    preserved across frames.
    """
    obj_id = obj_data.get('id')

    if obj_id in self._objects:
      obj = self._objects[obj_id]
    else:
      obj = SimpleNamespace()
      obj.chain_data = ChainData(regions={}, publishedLocations=[], persist={})

    obj.gid = obj_id
    obj.category = obj_data.get('type', obj_data.get('category'))
    obj.sceneLoc = Point(obj_data.get('translation', [0, 0, 0]))
    obj.velocity = (
      Point(obj_data['velocity']) if obj_data.get('velocity') else None
    )
    obj.size = obj_data.get('size')
    obj.confidence = obj_data.get('confidence')
    obj.frameCount = obj_data.get('frame_count', 0)
    obj.rotation = obj_data.get('rotation')
    obj.vectors = []
    obj.boundingBox = None
    obj.boundingBoxPixels = None
    obj.intersected = False
    obj.visibility = obj_data.get('visibility', [])
    obj.info = {'category': obj.category, 'confidence': obj.confidence}

    # Reconstruct bbMeters from size when available
    if obj.size and len(obj.size) == 3:
      _, width, height = obj.size
      obj.bbMeters = SimpleNamespace(
        size=Size(width, height), width=width, height=height
      )
    else:
      obj.bbMeters = None

    metadata = obj_data.get('metadata', {})
    obj.reid = metadata.get('reid') if metadata else {}
    obj.metadata = {}
    obj.similarity = obj_data.get('similarity')

    if obj_data.get('camera_bounds'):
      obj._camera_bounds = obj_data['camera_bounds']
    else:
      obj._camera_bounds = None

    self._resolve_timestamps(obj, obj_id, obj_data)

    obj.chain_data.regions = obj_data.get('regions', obj.chain_data.regions)
    obj.chain_data.persist = obj_data.get('persistent_data', obj.chain_data.persist)

    self._resolve_sensors(obj, obj_data.get('sensors', {}), sensors)

    hist = self._history.get(obj_id, {})
    obj.chain_data.publishedLocations = hist.get('publishedLocations', [])
    self._history.setdefault(obj_id, {})['publishedLocations'] = (
      obj.chain_data.publishedLocations
    )
    self._history[obj_id]['last_seen'] = obj.sceneLoc

    return obj

  def _resolve_timestamps(
    self, obj: SimpleNamespace, obj_id: str, obj_data: dict
  ) -> None:
    """Populate ``obj.first_seen`` and ``obj.when`` from data or history."""
    if 'first_seen' in obj_data:
      obj.first_seen = get_epoch_time(obj_data['first_seen'])
      obj.when = obj.first_seen
      self._history.setdefault(obj_id, {})['first_seen'] = obj.when
    elif obj_id in self._history and 'first_seen' in self._history[obj_id]:
      obj.first_seen = self._history[obj_id]['first_seen']
      obj.when = obj.first_seen
    else:
      current_time = get_epoch_time()
      obj.first_seen = current_time
      obj.when = current_time
      self._history.setdefault(obj_id, {})['first_seen'] = current_time
      log.debug(
        f"First time seeing object id {obj_id} from MQTT; "
        f"setting first_seen to current time: {current_time}"
      )

  def _resolve_sensors(
    self,
    obj: SimpleNamespace,
    sensors_data: dict,
    sensors: dict,
  ) -> None:
    """Populate ``chain_data`` sensor state from a per-object sensor payload."""
    for sensor_id, sensor_info in sensors_data.items():
      values = sensor_info.get('values', [])
      if not values:
        continue
      if self._is_environmental_sensor(sensor_id, sensors):
        obj.chain_data.env_sensor_state[sensor_id] = {'readings': values}
      else:
        obj.chain_data.attr_sensor_events[sensor_id] = values

  @staticmethod
  def _is_environmental_sensor(sensor_id: str, sensors: dict) -> bool:
    """Return ``True`` if *sensor_id* is environmental (the default)."""
    sensor = sensors.get(sensor_id) if sensors else None
    if sensor is not None and getattr(sensor, 'singleton_type', None) is not None:
      return sensor.singleton_type == 'environmental'
    return True
