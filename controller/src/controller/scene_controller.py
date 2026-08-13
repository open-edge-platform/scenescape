# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import orjson
import os
from collections import defaultdict
from types import SimpleNamespace

import ntplib

from scene_common.cache_manager import CacheManager
from controller.child_scene_controller import ChildSceneController
from scene_common.detections_builder import buildDetectionsList
from controller.external_source import ExternalSourcePoseCache, IdentityClaimRegistry
from controller.scene import Scene
from scene_common import log
from scene_common.geometry import Point, Region, Tripwire
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation
from scene_common.timestamp import adjust_time, get_epoch_time, get_iso_time
from scene_common.transform import applyChildTransform
from controller.observability import metrics
from controller.reid_env import (
  get_reid_client_cert,
  get_reid_client_key,
  get_reid_use_tls,
)
from controller.time_chunking import (DEFAULT_CHUNKING_RATE_FPS,
                                      MINIMAL_CHUNKING_RATE_FPS,
                                      MAXIMAL_CHUNKING_RATE_FPS)
from controller.tracking import EFFECTIVE_OBJECT_UPDATE_RATE, DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS
TRUSTED_POSITIONING_SOURCES_ENV_VAR = 'CONTROLLER_TRUSTED_POSITIONING_SOURCES'
EXTERNAL_SOURCE_BINDINGS_ENV_VAR = 'CONTROLLER_EXTERNAL_SOURCE_BINDINGS'


def _parseTrustedSources(value):
  """Parse a comma-separated list of source IDs authorized to publish poses
  already expressed in scene-local coordinates. Fails closed: an unset or
  empty value trusts no source."""
  if not value:
    return frozenset()
  return frozenset(item.strip() for item in value.split(',') if item.strip())

def _parseExternalSourceBindings(value):
  """Parse manual publisher→scene bindings.

  Format: ``publisher_id:scene_uid,publisher_id:scene_uid2,...``
  Returns a dict of publisher_id → frozenset(scene_uid). Empty/unset means
  no manual bindings (wgs84 publishers use geospatial auto-attach).
  """
  bindings = {}
  if not value:
    return bindings
  for item in value.split(','):
    item = item.strip()
    if not item:
      continue
    if ':' not in item:
      log.warning("Ignoring malformed %s entry (expected publisher:scene): %r",
                  EXTERNAL_SOURCE_BINDINGS_ENV_VAR, item)
      continue
    publisher_id, scene_uid = item.split(':', 1)
    publisher_id = publisher_id.strip()
    scene_uid = scene_uid.strip()
    if not publisher_id or not scene_uid:
      log.warning("Ignoring malformed %s entry: %r",
                  EXTERNAL_SOURCE_BINDINGS_ENV_VAR, item)
      continue
    bindings.setdefault(publisher_id, set()).add(scene_uid)
  return {publisher_id: frozenset(scenes) for publisher_id, scenes in bindings.items()}


class SceneController:

  def __init__(self, rewrite_bad_time, rewrite_all_time, max_lag, mqtt_broker,
               mqtt_auth, rest_url, rest_auth, client_cert, root_cert, ntp_server,
               tracker_config_file, schema_file, visibility_topic, data_source,
               reid_config_file=None, pose_adjustment_config_file=None):
    self.cert = client_cert
    self.root_cert = root_cert
    self.rewrite_bad_time = rewrite_bad_time
    self.rewrite_all_time = rewrite_all_time
    self.max_lag = max_lag
    self.broker = mqtt_broker
    self.mqtt_auth = mqtt_auth
    self.tracker_config_data = {}
    self.tracker_config_file = tracker_config_file
    self.reid_config_data = {}
    self.reid_config_file = reid_config_file
    self.pose_adjustment_config_data = {}
    self.pose_adjustment_config_file = pose_adjustment_config_file

    if tracker_config_file is not None:
      self.extractTrackerConfigData(tracker_config_file)

    if reid_config_file is not None:
      self.extractReidConfigData(reid_config_file)

    if pose_adjustment_config_file is not None:
      self.extractPoseAdjustmentConfigData(pose_adjustment_config_file)

    self.last_time_sync = None
    self.ntp_server = ntp_server
    self.ntp_client = ntplib.NTPClient()
    self.time_offset = 0

    self.schema_val = SchemaValidation(schema_file, is_multi_message=True)

    self.pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)
    self.pubsub.onConnect = self.onConnect
    self.pubsub.connect()

    self.cache_manager = CacheManager(
      data_source,
      rest_url,
      rest_auth,
      root_cert,
      self.tracker_config_data,
      self.reid_config_data,
      self.pose_adjustment_config_data,
    )

    self.visibility_topic = visibility_topic
    log.info(f"Publishing camera visibility info on {self.visibility_topic} topic.")

    self.external_source_pose_cache = ExternalSourcePoseCache(
      sweep_grace_seconds=self.max_lag,
      sweep_time_provider=self._getExternalSourceSweepTime)
    self.identity_claim_registry = IdentityClaimRegistry(
      sweep_grace_seconds=self.max_lag,
      sweep_time_provider=self._getExternalSourceSweepTime)
    # Expired-entry cleanup runs on a background daemon timer rather than
    # inline on the MQTT message-handling thread, so a burst of accumulated
    # entries never stalls ingestion (see external_source.py).
    self.external_source_pose_cache.startBackgroundSweep()
    self.identity_claim_registry.startBackgroundSweep()
    self.trusted_positioning_sources = _parseTrustedSources(
      os.getenv(TRUSTED_POSITIONING_SOURCES_ENV_VAR))
    self.external_source_bindings = _parseExternalSourceBindings(
      os.getenv(EXTERNAL_SOURCE_BINDINGS_ENV_VAR))
    if self.external_source_bindings:
      log.info("Loaded %s manual external-source bindings for %s publishers",
               EXTERNAL_SOURCE_BINDINGS_ENV_VAR, len(self.external_source_bindings))
    return

  def extractTrackerConfigData(self, tracker_config_file):
    if not os.path.exists(tracker_config_file) and not os.path.isabs(tracker_config_file):
      script = os.path.realpath(__file__)
      tracker_config_file = os.path.join(os.path.dirname(script), tracker_config_file)
    with open(tracker_config_file) as json_file:
      tracker_config = orjson.loads(json_file.read())
      self.tracker_config_data["max_unreliable_time"] = tracker_config["max_unreliable_time_s"]
      self.tracker_config_data["non_measurement_time_dynamic"] = tracker_config["non_measurement_time_dynamic_s"]
      self.tracker_config_data["non_measurement_time_static"] = tracker_config["non_measurement_time_static_s"]
      self.tracker_config_data["effective_object_update_rate"] = self._extractTrackerRate(tracker_config, "effective_object_update_rate", EFFECTIVE_OBJECT_UPDATE_RATE)
      self._extractTimeChunkingEnabled(tracker_config)
      self.tracker_config_data["time_chunking_rate_fps"] = self._extractTrackerRate(tracker_config, "time_chunking_rate_fps", DEFAULT_CHUNKING_RATE_FPS, MINIMAL_CHUNKING_RATE_FPS, MAXIMAL_CHUNKING_RATE_FPS)
      self.tracker_config_data["suspended_track_timeout_secs"] = tracker_config.get("suspended_track_timeout_secs", DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS)

      if "persist_attributes" in tracker_config:
        if isinstance(tracker_config["persist_attributes"], dict):
          self.tracker_config_data["persist_attributes"] = tracker_config["persist_attributes"]
        else:
          log.error("Invalid persist_attributes format in tracker config file")
          self.tracker_config_data["persist_attributes"] = {}
    return

  def extractReidConfigData(self, reid_config_file):
    """Extract REID configuration from reid-config.json file"""
    if not os.path.exists(reid_config_file) and not os.path.isabs(reid_config_file):
      script = os.path.realpath(__file__)
      reid_config_file = os.path.join(os.path.dirname(script), reid_config_file)
    with open(reid_config_file) as json_file:
      reid_config = orjson.loads(json_file.read())
      self.reid_config_data = reid_config
      log.info(f"Loaded REID configuration from {reid_config_file}: {self.reid_config_data}")
    return

  def extractPoseAdjustmentConfigData(self, pose_adjustment_config_file):
    """Extract pose adjustment routing configuration from pose-adjustment-route.json file"""
    if not os.path.exists(pose_adjustment_config_file) and not os.path.isabs(pose_adjustment_config_file):
      script = os.path.realpath(__file__)
      pose_adjustment_config_file = os.path.join(os.path.dirname(script), pose_adjustment_config_file)
    with open(pose_adjustment_config_file) as json_file:
      pose_adjustment_config = orjson.loads(json_file.read())
      self.pose_adjustment_config_data = pose_adjustment_config
      log.info(
        f"Loaded pose adjustment configuration from {pose_adjustment_config_file}: "
        f"{self.pose_adjustment_config_data}"
      )
    return

  def _extractTrackerRate(self, tracker_config, parameter_name, default_rate, min_rate=None, max_rate=None):
    """Extract and validate rate parameter from tracker config."""

    if parameter_name not in tracker_config:
      log.warning(f"{parameter_name} not specified in tracker configuration, will use default rate of {default_rate} fps.")
      return default_rate

    try:
      rate_fps = int(tracker_config[parameter_name])
      if rate_fps <= 0:
        raise ValueError(f"{parameter_name} must be a positive integer.")
      if min_rate is not None and rate_fps < min_rate:
        raise ValueError(f"{parameter_name} must be at least {min_rate}.")
      if max_rate is not None and rate_fps > max_rate:
        raise ValueError(f"{parameter_name} must be at most {max_rate}.")
      log.info(f"{parameter_name}: {rate_fps}")
      return rate_fps
    except (ValueError, TypeError) as e:
      raise ValueError(f"Invalid value for {parameter_name} in tracker configuration") from e

  def _extractTimeChunkingEnabled(self, tracker_config):
    """Extract and validate time_chunking_enabled flag"""
    if "time_chunking_enabled" not in tracker_config:
      log.warning("Time chunking enabled flag missing in tracker config file, enabling time chunking.")
      self.tracker_config_data["time_chunking_enabled"] = True
      return

    try:
      self.tracker_config_data["time_chunking_enabled"] = bool(tracker_config["time_chunking_enabled"])
      log.info(f"Time chunking enabled: {self.tracker_config_data['time_chunking_enabled']}")
    except (ValueError, TypeError):
      raise ValueError("Invalid value for time_chunking_enabled in tracker config file.")
    return

  def loopForever(self):
    return self.pubsub.loopForever()

  def _getExternalSourceSweepTime(self):
    """Return the NTP-corrected time used to accept external-source events."""
    return get_epoch_time() + self.time_offset

  def shutdown(self):
    """Stop background maintenance threads owned by this controller.

    Safe to call multiple times. The MQTT/tracker threads are not joined
    here since ``loopForever()`` normally only returns on process exit, at
    which point these daemon threads are torn down anyway; this exists for
    graceful cleanup paths (tests, future signal handling).
    """
    self.external_source_pose_cache.stopBackgroundSweep()
    self.identity_claim_registry.stopBackgroundSweep()
    return

  def publishDetections(self, scene, objects, ts, otype, jdata, camera_id):
    if not hasattr(scene, 'lastPubCount'):
      scene.lastPubCount = {}

    if not hasattr(scene, 'last_published_detection'):
      scene.last_published_detection = defaultdict(lambda: None)
    metric_attributes = {
      "camera": camera_id if camera_id is not None else "unknown",
      "category": otype,
      "scene": scene.name
    }
    metrics.record_object_count(len(objects), metric_attributes)

    self.publishSceneDetections(scene, objects, otype, jdata)
    return

  def shouldPublish(self, last, now, max_delay):
    return last is None or now - last >= max_delay

  def publishSceneDetections(self, scene, objects, otype, jdata):
    # Full rate output (30fps): exclude sensor data for performance
    jdata['objects'] = buildDetectionsList(objects, scene, self.visibility_topic == 'unregulated', include_sensors=False)
    olen = len(jdata['objects'])
    cid = scene.name + "/" + otype
    if olen > 0 or cid not in scene.lastPubCount or scene.lastPubCount[cid] > 0:
      if 'debug_hmo_start_time' in jdata:
        jdata['debug_hmo_processing_time'] = get_epoch_time() - jdata['debug_hmo_start_time']
      # Convert numpy types to native Python types for JSON serialization
      jstr = orjson.dumps(jdata, option=orjson.OPT_SERIALIZE_NUMPY)
      new_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene.uid,
                                     thing_type=otype)
      self.pubsub.publish(new_topic, jstr)
      scene.lastPubCount[cid] = olen
    self.publishExternalDetections(scene, otype, objects, jdata)
    return


  def publishExternalDetections(self, scene, otype, objects, jdata_base):
    # Hierarchy output for parent scenes. Root scenes (no parent) have no
    # hierarchy consumer for this path — skip rather than publishing onto
    # scenescape/external/{scene_uid}/+ (publisher id = this scene).
    if not getattr(scene, 'parent', None):
      return

    # External rate output (0.5fps)
    now = get_epoch_time()
    is_clearing_event = len(objects) == 0
    if is_clearing_event or self.shouldPublish(scene.last_published_detection[otype], now, 1/scene.external_update_rate):
      scene.last_published_detection[otype] = get_epoch_time()

      # Rebuild detections list with sensor data included
      reid_policy = self._hierarchyReidPublishPolicy(scene)
      will_enroll = reid_policy == 'will_enroll'
      jdata = jdata_base.copy()
      jdata['objects'] = buildDetectionsList(
        objects, scene, self.visibility_topic == 'unregulated', include_sensors=True,
        attach_reid_provenance=True,
        minimum_bbox_area=scene.reid_config_data.get('minimum_bbox_area'),
        will_enroll_reid=will_enroll,
        withhold_reid=(reid_policy == 'withhold'),
        reid_enrolled_fn=(
          (lambda aobj, _scene=scene: self._trackHasReidEnrollment(_scene, aobj))
          if will_enroll else None))
      jstr = orjson.dumps(jdata, option=orjson.OPT_SERIALIZE_NUMPY)

      scene_hierarchy_topic = PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=scene.uid,
                                                 thing_type=otype)
      self.pubsub.publish(scene_hierarchy_topic, jstr)
    return

  def _sceneHasReidWriteIntent(self):
    """
    True when this controller is configured to own ReID database writes.

    TLS deployments mount client certs only on ReID-enabled compose profiles;
    parent-only / passthrough children keep the TLS default and omit those certs.
    Setting REID_USE_TLS=false is an explicit non-mTLS ReID choice and implies
    write intent even when hostname/database env vars use built-in defaults.
    """
    if get_reid_use_tls():
      return (os.path.exists(get_reid_client_cert())
              and os.path.exists(get_reid_client_key()))
    return True

  def _hierarchyReidPublishPolicy(self, scene):
    """
    Decide how hierarchy output should treat ReID embeddings for this scene.

    Returns one of:
      - 'will_enroll': write intent exists and at least one successful write was
        confirmed — enable per-track will_enroll/enrolled stamps so parents skip
        writes for tracks this child owns. Survives later write-health or
        reid_enabled clears so parents do not sole-enroll crops already stored.
      - 'withhold': ReID write intent exists but schema is not ready yet, or no
        successful write has been confirmed yet (and no empty-batch fallback) —
        do not forward *local* embeddings (avoids parent sole-enroll before the
        child can write, and avoids claiming will_enroll when the child cannot
        enroll). Inherited vetted embeddings still forward.
      - 'passthrough': no local ReID write path, writes are failing before the
        first confirm, or empty batches occurred before the first confirmed write
        — forward vetted crops without will_enroll so the parent may sole-enroll.
        Local enrollment also stops in those handoff modes so the child does not
        keep writing under passthrough.
    """
    tracker = getattr(scene, 'tracker', None)
    uuid_manager = getattr(tracker, 'uuid_manager', None) if tracker is not None else None
    if uuid_manager is None:
      return 'passthrough'
    if not self._sceneHasReidWriteIntent():
      return 'passthrough'
    # Confirmed writes keep will_enroll mode even if reid later disables or
    # write-health clears — per-track stamps limit claims to owned tracks.
    if getattr(uuid_manager, 'reid_write_confirmed', False):
      return 'will_enroll'
    if not getattr(uuid_manager, 'reid_enabled', False):
      return 'passthrough'
    if not getattr(uuid_manager, 'reid_write_healthy', True):
      return 'passthrough'
    if getattr(uuid_manager, 'reid_empty_batch_before_confirm', False):
      return 'passthrough'
    database = getattr(uuid_manager, 'reid_database', None)
    if getattr(database, '_schema_ready', False) is not True:
      return 'withhold'
    return 'withhold'

  def _trackHasReidEnrollment(self, scene, aobj):
    """True when this track owns or is accumulating a local ReID write."""
    tracker = getattr(scene, 'tracker', None)
    uuid_manager = getattr(tracker, 'uuid_manager', None) if tracker is not None else None
    if uuid_manager is None:
      return False
    rv_id = getattr(aobj, 'rv_id', None)
    if rv_id is None:
      return False
    entry = uuid_manager.features_for_database.get(rv_id)
    if entry and entry.get('reid_vectors'):
      return True
    if uuid_manager.enrollment_features.get(rv_id):
      return True
    if uuid_manager.local_enrollment_features.get(rv_id):
      return True
    if uuid_manager.quality_features.get(rv_id):
      return True
    if rv_id in uuid_manager.active_query:
      return True
    with uuid_manager.active_ids_lock:
      values = uuid_manager.active_ids.get(rv_id)
    return bool(values and values[0] is not None)
  # Message handling
  def handleMovingObjectMessage(self, client, userdata, message):

    topic = PubSub.parseTopic(message.topic)
    jdata = orjson.loads(message.payload.decode('utf-8'))

    metric_attributes = {
        "topic": message.topic,
        "camera": jdata.get("id", "unknown"),
    }
    metrics.inc_messages(metric_attributes)
    with metrics.time_mqtt_handler(metric_attributes):
      if 'camera_id' in topic and not self.schema_val.validateMessage("detector", jdata):
        return

      if topic['_topic_id'] == PubSub.DATA_EXTERNAL and 'source_id' in jdata \
          and not self.schema_val.validateMessage("external_source", jdata):
        return

      now = get_epoch_time()
      self.time_offset, self.last_time_sync = adjust_time(now, self.ntp_server, self.ntp_client,
                                                      self.last_time_sync, self.time_offset,
                                                      ntplib.NTPException)
      now += self.time_offset
      if 'updatecamera' in jdata:
        return

      jdata['debug_hmo_start_time'] = now
      # Camera intrinsics/distortion refresh only applies to camera-originated
      # messages (keyed by 'id'); external-source messages are keyed by
      # 'source_id' and have no camera parameters to refresh.
      if topic['_topic_id'] != PubSub.DATA_EXTERNAL:
        self.cache_manager.refreshScenesForCamParams(jdata)

      if self.rewrite_all_time:
        msg_when = now
        jdata['timestamp'] = get_iso_time(now)
      else:
        msg_when = get_epoch_time(jdata['timestamp'])

      lag = abs(now - msg_when)
      if lag > self.max_lag:
        if not self.rewrite_bad_time:
          metric_attributes["reason"] = "fell_behind"
          metrics.inc_dropped(metric_attributes)
          log.warning("{} FELL BEHIND by {}. SKIPPING {}".format(
            message.topic, lag, jdata.get('id', jdata.get('source_id', 'unknown'))))
          return
        msg_when = now

      camera_id = None
      if topic['_topic_id'] == PubSub.DATA_EXTERNAL:
        detection_types = [topic['thing_type']]
        # Path segment is the publisher id (child scene uid or agent source_id).
        publisher_id = topic['scene_id']
        if 'source_id' in jdata:
          if jdata['source_id'] != publisher_id:
            log.error("External source_id %r does not match topic publisher id %r",
                      jdata['source_id'], publisher_id)
            return
          scenes = self._scenesForExternalPublisher(publisher_id, jdata, msg_when)
          if not scenes:
            log.warning("No scene binding for external publisher %s", publisher_id)
            return
          for scene in scenes:
            jdata_scene = dict(jdata)
            jdata_scene['objects'] = [dict(obj) for obj in jdata.get('objects', [])]
            success = self._handleExternalSourceObject(
              scene, jdata_scene, detection_types[0], msg_when)
            if not success:
              log.error("Camera fail publisher_id=%s scene=%s", publisher_id, getattr(scene, 'name', None))
              self.cache_manager.invalidate()
              return
            jdata_scene['id'] = scene.uid
            jdata_scene['name'] = scene.name
            for detection_type in detection_types:
              jdata_scene['unique_detection_count'] = scene.tracker.getUniqueIDCount(
                detection_type)
              self.publishDetections(
                scene, scene.tracker.currentObjects(detection_type),
                msg_when, detection_type, jdata_scene, camera_id)
          return

        handled = self._handleChildSceneObject(
          publisher_id, jdata, detection_types[0], msg_when)
        # None => orphan hierarchy echo from a root scene; ignore.
        if handled is None:
          return
        success, scene = handled
        sender_id = publisher_id
      else:
        detection_types = jdata['objects'].keys()
        camera_id = sender_id = topic['camera_id']
        sender = self.cache_manager.sceneWithCameraID(sender_id)
        if sender is None:
          log.error(f"UNKNOWN SENDER: {sender_id}")
          return
        scene = sender

        # If no detection types in the message, add empty arrays for all tracked types
        # This must be done BEFORE processCameraData so the tracker processes them
        if not detection_types:
          detection_types = list(scene.tracker.trackers.keys())
          for dtype in detection_types:
            jdata['objects'][dtype] = []

        success = scene.processCameraData(jdata, when=msg_when)

      if not success:
        log.error("Camera fail", sender_id, scene.name if scene is not None else "unknown")
        self.cache_manager.invalidate()
        return

      jdata['id'] = scene.uid
      jdata['name'] = scene.name
      for detection_type in detection_types:
        jdata['unique_detection_count'] = scene.tracker.getUniqueIDCount(detection_type)
        self.publishDetections(scene, scene.tracker.currentObjects(detection_type),
                              msg_when, detection_type, jdata, camera_id)
      return

  def _handleChildSceneObject(self, sender_id, jdata, detection_type, msg_when):
    is_remote = False
    sender = self.cache_manager.sceneWithID(sender_id)
    if sender is None:
      remote_sender = self.cache_manager.sceneWithRemoteChildID(sender_id)
      if remote_sender is None:
        log.error(f"UNKNOWN SENDER: {sender_id}")
        return False, None
      sender = remote_sender
      is_remote = True

    if not hasattr(sender, 'parent') or sender.parent is None:
      if is_remote:
        recovered = self._parentUidForRemoteChild(sender_id)
        if recovered:
          sender.parent = recovered
          log.info(f"Recovered parent={recovered} for remote child {sender_id}")
        else:
          log.error("UNKNOWN PARENT", sender_id)
          return False, sender
      else:
        # Hierarchy publishes (no source_id) from a root scene are not destined
        # for a parent — ignore them rather than failing closed and invalidating
        # the scene cache. (Root scenes no longer self-subscribe for ingest.)
        log.debug("Ignoring hierarchy publish from root scene %s (no parent)",
                  sender_id)
        return None

    scene = self.cache_manager.sceneWithID(sender.parent)
    if scene is None:
      log.error("PARENT SCENE NOT FOUND", sender.parent, "for sender", sender.name)
      return False, None

    success = scene.processSceneData(jdata, sender, sender.cameraPose,
                                     detection_type, when=msg_when)
    return success, scene

  def _scenesForExternalPublisher(self, publisher_id, jdata, msg_when):
    """Resolve which scenes should ingest a publisher-centric external message.

    Manual bindings from CONTROLLER_EXTERNAL_SOURCE_BINDINGS win when present
    for this publisher. Otherwise:
    - ``reference_frame: wgs84`` → every scene with geospatial calibration
      (interim auto-attach until a spatial binder with footprint/handoff policy
      exists)
    - pose omitted → scenes that still hold a live cached pose for this source
    - ``reference_frame: scene`` without a manual binding → no scenes (must be
      explicitly bound)
    """
    explicit = self.external_source_bindings.get(publisher_id)
    if explicit is not None:
      scenes = []
      for scene_uid in explicit:
        scene = self.cache_manager.sceneWithID(scene_uid)
        if scene is None:
          log.warning("External binding scene %s not found for publisher %s",
                      scene_uid, publisher_id)
        else:
          scenes.append(scene)
      return scenes

    pose = jdata.get('pose')
    if pose is None:
      scene_uids = self.external_source_pose_cache.scenesWithLiveCache(
        publisher_id, msg_when)
      scenes = []
      for scene_uid in scene_uids:
        scene = self.cache_manager.sceneWithID(scene_uid)
        if scene is not None:
          scenes.append(scene)
      return scenes

    reference_frame = pose.get('reference_frame')
    if reference_frame == 'wgs84':
      scenes = []
      for scene in self.cache_manager.allScenes():
        if scene.trs_xyz_to_lla is not None:
          scenes.append(scene)
      return scenes

    # scene-frame (and unknown frames) require an explicit manual binding.
    return []

  def _handleExternalSourceObject(self, scene, jdata, detection_type, msg_when):
    """Handle a message from a dynamic external source (physical agent or
    positioning service) publishing under its own publisher id, as
    distinguished from a configured child scene by the presence of
    'source_id' in the payload."""
    source_id = jdata['source_id']
    trusted = source_id in self.trusted_positioning_sources
    camera_pose, reason = self.external_source_pose_cache.resolve(
      scene, source_id, jdata.get('pose'), msg_when, trusted_scene_pose=trusted)
    if camera_pose is None:
      log.warning(f"External source pose unavailable for source={source_id} "
                f"scene={scene.uid}: {reason}")
      return True

    # Every external-source object's 'id' is trusted directly as global
    # track identity by default (no source allowlist to configure): the
    # object bypasses Scenescape's kinematic tracker/ReID association and
    # keeps the source-assigned id as its gid for as long as the source
    # keeps reporting that same id. This is safe for sources like a UWB/RTLS
    # tag whose id is already a permanent hardware identifier. To keep this
    # safe without requiring per-source configuration, each id is claimed
    # exclusively per (scene, category): if a different source is already
    # using the same id at the same time -- a genuine identity collision --
    # the newly arriving, colliding object is dropped rather than silently
    # merged into an unrelated track. See IdentityClaimRegistry for the one
    # case this does not solve (a single source reusing a stale id for a
    # new physical object after its previous claim has expired).
    accepted_objects = []
    for obj in jdata.get('objects', []):
      obj_id = obj.get('id')
      ok, collision_reason = self.identity_claim_registry.claim(
        scene.uid, detection_type, source_id, obj_id, msg_when)
      if ok:
        accepted_objects.append(obj)
      else:
        log.warning(
          f"Rejecting external-source object: id={obj_id} from source={source_id} "
          f"scene={scene.uid} category={detection_type}: {collision_reason}")
    jdata['objects'] = accepted_objects

    external_source = SimpleNamespace(name=source_id, uid=source_id, retrack=False)
    return scene.processSceneData(jdata, external_source, camera_pose,
                                  detection_type, when=msg_when)

  @staticmethod
  def _withRemoteChildParent(info, parent_uid):
    """Copy remote-child REST *info* and ensure ``parent`` is set to *parent_uid*."""
    remote_info = dict(info)
    if not remote_info.get('parent'):
      remote_info['parent'] = parent_uid
    return remote_info

  def _parentUidForRemoteChild(self, remote_child_id):
    """Return the parent scene uid that links *remote_child_id*, or None."""
    for scene in self.cache_manager.allScenes():
      results = self.cache_manager.data_source.getChildScenes(scene.uid)
      for info in (results or {}).get('results', []):
        if str(info.get('remote_child_id')) == str(remote_child_id):
          return scene.uid
    return None

  def updateCameras(self):
    for scene in self.scenes:
      for camera in scene.cameras:
        cam = scene.cameras[camera]
        if not hasattr(cam, "pose"):
          self.cache_manager.updateCamera(cam)
    return

  def handleDatabaseMessage(self, client, userdata, message):
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      try:
        self.updateSubscriptions()
        self.updateObjectClasses()
        self.updateCameras()
        self.updateTRSMatrix()
      except Exception as e:
        log.warning("Failed to update database: %s", e)
    return

  # MQTT callbacks
  def onConnect(self, client, userdata, flags, rc):
    log.info("Connected with result code", rc)
    if rc != 0:
      exit(1)
    self.subscribed = set()
    self.updateSubscriptions()
    self.updateObjectClasses()
    self.updateTRSMatrix()
    topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
    self.pubsub.addCallback(topic, self.handleDatabaseMessage)
    log.info("Subscribed to", topic)
    # FIXME - update subscriptions when scenes/sensors/children added/deleted/renamed
    return

  def updateObjectClasses(self):
    results = self.cache_manager.data_source.getAssets()
    if results and 'results' in results:
      for scene in self.scenes:
        if scene.tracker is not None:
          scene.tracker.updateObjectClasses(results['results'])
    return

  def updateTRSMatrix(self):
    for scene in self.cache_manager.allScenes():
      if scene.trs_xyz_to_lla is not None:
        res = self.cache_manager.data_source.setTRSMatrix(scene.uid, scene.trs_xyz_to_lla)
        if res.errors:
          log.info(
                  "Failed to update trs matrix for scene %s. Errors: %s",
                  scene.name,
                  res.errors,
                )
    return

  def republishEvents(self, client, userdata, message):
    """
    Republishes the child analytics under parent topic that
    enables parent to visualize them.
    """
    topic = PubSub.parseTopic(message.topic)
    msg = orjson.loads(message.payload.decode('utf-8'))

    sender_id = topic['scene_id']
    sender = self.cache_manager.sceneWithID(sender_id)
    if sender is None:
      remote_sender = self.cache_manager.sceneWithRemoteChildID(sender_id)
      if remote_sender is None:
        log.error(f"UNKNOWN SENDER: {sender_id}")
        return
      else:
        sender = remote_sender

    if not hasattr(sender, 'parent') or sender.parent is None:
      log.error("UNKNOWN PARENT", sender_id)
      return

    scene = self.cache_manager.sceneWithID(sender.parent)
    event_topic = PubSub.formatTopic(PubSub.EVENT,
                                      region_type=topic['region_type'], event_type=topic['event_type'],
                                      scene_id=scene.uid, region_id=topic['region_id'])

    self.transformObjectsinEvent(msg, sender)

    msg['metadata'] = applyChildTransform(msg['metadata'], sender.cameraPose)
    if 'from_child_scene' not in msg['metadata']:
      msg['metadata']['from_child_scene'] = sender.name
    else:
      msg['metadata']['from_child_scene'] = sender.name + " > " + msg['metadata']['from_child_scene']
    self.pubsub.publish(event_topic, orjson.dumps(msg, option=orjson.OPT_SERIALIZE_NUMPY))
    return

  def transformObjectsinEvent(self, event, sender):
    keys = ['objects', 'entered', 'exited']
    for k in keys:
      if k == 'exited':
        for i, obj in enumerate(event[k]):
          event[k][i]['object']['translation'] = sender.cameraPose.cameraPointToWorldPoint(
                                                            Point(obj['object']['translation'])).asNumpyCartesian.tolist()
      else:
        for i, obj in enumerate(event[k]):
          event[k][i]['translation'] = sender.cameraPose.cameraPointToWorldPoint(
                                                            Point(obj['translation'])).asNumpyCartesian.tolist()
    return

  def updateSubscriptions(self):
    log.debug("UPDATE SUBSCRIPTIONS")
    self.cache_manager.invalidate()
    if not hasattr(self, 'subscribed'):
      self.subscribed = set()
    need_subscribe = set()

    if not hasattr(self, 'subscribed_children'):
      self.subscribed_children = dict()
    need_subscribe_child = dict()

    self.scenes = self.cache_manager.allScenes()
    # Publisher-centric: one wildcard covers configured children and dynamic
    # agents on scenescape/external/{publisher_id}/{thing_type}.
    need_subscribe.add((PubSub.formatTopic(PubSub.DATA_EXTERNAL,
                                          scene_id="+", thing_type="+"),
                        self.handleMovingObjectMessage))

    for scene in self.scenes:
      for camera in scene.cameras:
        need_subscribe.add((PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera),
                            self.handleMovingObjectMessage))
      # External publisher-centric ingest is covered by the wildcard subscribe above.

      if hasattr(scene, 'children'):
        child_scenes = self.cache_manager.data_source.getChildScenes(scene.uid)

        for info in child_scenes.get('results', []):
          if info['child_type'] == 'local':
            self.cache_manager.sceneWithID(info['child']).retrack = info['retrack']

            need_subscribe.add((PubSub.formatTopic(PubSub.EVENT, region_type="+",
                                                  event_type="+",
                                                  scene_id=info['child'],
                                                  region_id="+"),
                                self.republishEvents))
          else:
            # Remote child payloads may omit parent (or leave it null). The
            # enclosing scene is the parent by construction of this query.
            remote_info = self._withRemoteChildParent(info, scene.uid)
            child_obj = ChildSceneController(self.root_cert, remote_info, self)
            self.cache_manager.cached_child_transforms_by_uid[remote_info['remote_child_id']] = \
              Scene.deserialize(remote_info)
            need_subscribe_child[remote_info['remote_child_id']] = child_obj
            need_subscribe.add((PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS,
                                                    scene_id=remote_info['remote_child_id']),
                                child_obj.publishStatus))

    # disconnect old children clients
    for old_child, cobj in self.subscribed_children.items():
      if old_child not in need_subscribe_child:
        self.cache_manager.cached_child_transforms_by_uid.pop(old_child, 'None')
      cobj.loopStop()

    # connect to all children
    for new_child, cobj in need_subscribe_child.items():
      log.info(f"Connecting to remote child {new_child}")
      cobj.loopStart()

    self.subscribed_children = need_subscribe_child

    new = need_subscribe - self.subscribed
    old = self.subscribed - need_subscribe
    for topic, callback in old:
      self.pubsub.removeCallback(topic)
      log.info("Unsubscribed from", topic)
    for topic, callback in new:
      self.pubsub.addCallback(topic, callback)
      log.info("Subscribed to", topic)
    self.subscribed = need_subscribe
    return
