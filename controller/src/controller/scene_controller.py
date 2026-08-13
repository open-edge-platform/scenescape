# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import orjson
import os
from collections import defaultdict

import ntplib

from scene_common.cache_manager import CacheManager
from controller.child_scene_controller import ChildSceneController
from scene_common.detections_builder import buildDetectionsList
from controller.scene import Scene
from scene_common import log
from scene_common.geometry import Point, Region, Tripwire
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation
from scene_common.timestamp import adjust_time, get_epoch_time, get_iso_time
from scene_common.transform import applyChildTransform
from controller.observability import metrics
from controller.time_chunking import (DEFAULT_CHUNKING_RATE_FPS,
                                      MINIMAL_CHUNKING_RATE_FPS,
                                      MAXIMAL_CHUNKING_RATE_FPS)
from controller.tracking import EFFECTIVE_OBJECT_UPDATE_RATE, DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS

AVG_FRAMES = 100

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
    self.regulate_cache = {}
    log.info(f"Publishing camera visibility info on {self.visibility_topic} topic.")
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
    self.publishRegulatedDetections(scene, objects, otype, jdata, camera_id)
    return

  def shouldPublish(self, last, now, max_delay):
    return last is None or now - last >= max_delay

  def publishRegulatedDetections(self, scene_obj, msg_objects, otype, jdata, camera_id):
    """Publish tracked objects and the current pose of every scene camera."""
    update_rate = self.calculateRate()
    scene_uid = scene_obj.uid

    if scene_uid not in self.regulate_cache:
      self.regulate_cache[scene_uid] = {
        'objects': {},
        'rate': {},
        'last': None,
      }
    scene = self.regulate_cache[scene_uid]
    scene['objects'][otype] = buildDetectionsList(
      msg_objects, scene_obj, self.visibility_topic == 'unregulated',
      include_sensors=True, include_region_dwell=True)
    if camera_id is not None:
      scene['rate'][camera_id] = jdata.get('rate')

    now = get_epoch_time()
    if self.shouldPublish(scene['last'], now, 1 / scene_obj.regulated_rate):
      objects = [obj for category_objects in scene['objects'].values() for obj in category_objects]
      new_jdata = {
        'timestamp': jdata['timestamp'],
        'objects': objects,
        'cameras': scene_obj.serializeCameras(),
        'id': jdata['id'],
        'name': jdata['name'],
        'scene_rate': round(1 / update_rate, 1),
        'rate': scene['rate'],
      }
      jstr = orjson.dumps(new_jdata, option=orjson.OPT_SERIALIZE_NUMPY)
      topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
      self.pubsub.publish(topic, jstr)
      scene['last'] = now
    return

  def calculateRate(self):
    now = get_epoch_time()
    if not hasattr(self, 'regulate_rate'):
      self.regulate_last = now
      self.regulate_rate = 1
    delta = now - self.regulate_last
    self.regulate_rate = (self.regulate_rate * AVG_FRAMES + delta) / (AVG_FRAMES + 1)
    self.regulate_last = now
    return self.regulate_rate

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
      self.publishExternalDetections(scene, otype, objects, jdata)
      scene.lastPubCount[cid] = olen
    return

  def publishExternalDetections(self, scene, otype, objects, jdata_base):
    # External rate output (0.5fps)
    now = get_epoch_time()
    if self.shouldPublish(scene.last_published_detection[otype], now, 1/scene.external_update_rate):
      scene.last_published_detection[otype] = get_epoch_time()

      jdata = jdata_base.copy()
      jdata['objects'] = buildDetectionsList(objects, scene, self.visibility_topic == 'unregulated', include_sensors=False)
      jstr = orjson.dumps(jdata, option=orjson.OPT_SERIALIZE_NUMPY)

      scene_hierarchy_topic = PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=scene.uid,
                                                 thing_type=otype)
      self.pubsub.publish(scene_hierarchy_topic, jstr)
    return

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

      now = get_epoch_time()
      self.time_offset, self.last_time_sync = adjust_time(now, self.ntp_server, self.ntp_client,
                                                      self.last_time_sync, self.time_offset,
                                                      ntplib.NTPException)
      now += self.time_offset
      if 'updatecamera' in jdata:
        return

      jdata['debug_hmo_start_time'] = now
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
          log.warning("{} FELL BEHIND by {}. SKIPPING {}".format(message.topic, lag, jdata['id']))
          return
        msg_when = now

      camera_id = None
      if topic['_topic_id'] == PubSub.DATA_EXTERNAL:
        detection_types = [topic['thing_type']]
        sender_id = topic['scene_id']
        success, scene = self._handleChildSceneObject(sender_id, jdata, detection_types[0], msg_when)
      else:
        detection_types = jdata['objects'].keys()
        camera_id = sender_id = topic['camera_id']
        sender = self.cache_manager.sceneWithCameraID(sender_id)
        if sender is None:
          log.error("UNKNOWN SENDER", sender_id)
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
        log.error("Camera fail", sender_id, scene.name)
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
    sender = self.cache_manager.sceneWithID(sender_id)
    if sender is None:
      remote_sender = self.cache_manager.sceneWithRemoteChildID(sender_id)
      if remote_sender is None:
        log.error("UNKNOWN SENDER")
        return
      else:
        sender = remote_sender

    if not hasattr(sender, 'parent') or sender.parent is None:
      log.error("UNKNOWN PARENT", sender_id)
      return False, sender

    scene = self.cache_manager.sceneWithID(sender.parent)
    success = scene.processSceneData(jdata, sender, sender.cameraPose,
                                     detection_type, when=msg_when)
    return success, scene

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
        log.error("UNKNOWN SENDER")
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
    for scene in self.scenes:
      for camera in scene.cameras:
        need_subscribe.add((PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera),
                            self.handleMovingObjectMessage))

      if hasattr(scene, 'children'):
        child_scenes = self.cache_manager.data_source.getChildScenes(scene.uid)

        for info in child_scenes.get('results', []):
          if info['child_type'] == 'local':
            self.cache_manager.sceneWithID(info['child']).retrack = info['retrack']

            need_subscribe.add((PubSub.formatTopic(PubSub.DATA_EXTERNAL,
                                                   scene_id=info['child'], thing_type="+"),
                                self.handleMovingObjectMessage))

            need_subscribe.add((PubSub.formatTopic(PubSub.EVENT, region_type="+",
                                                  event_type="+",
                                                  scene_id=info['child'],
                                                  region_id="+"),
                                self.republishEvents))
          else:
            child_obj = ChildSceneController(self.root_cert, info, self)
            self.cache_manager.cached_child_transforms_by_uid[info['remote_child_id']] = Scene.deserialize(info)
            need_subscribe_child[info['remote_child_id']] = child_obj
            need_subscribe.add((PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_id=info['remote_child_id']), child_obj.publishStatus))

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
