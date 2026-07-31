# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import orjson
from collections import defaultdict
from pathlib import Path

from analytics.adapters.scene_model import AnalyticsScene
from analytics.event_publisher import publish_events
from scene_common.cache_manager import CacheManager
from scene_common.detections_builder import buildDetectionsList, computeCameraBounds
from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation
from scene_common.timestamp import get_epoch_time, get_iso_time

AVG_FRAMES = 100


class AnalyticsService:
  """MQTT controller for the standalone analytics service.

  Equivalent to SceneController in analytics-only mode, but with all
  tracker, Re-ID, pose-adjustment, NTP, and camera-data paths removed.
  Instantiate and call loopForever() to run.
  """

  def __init__(self, rewrite_all_time, mqtt_broker,
               mqtt_auth, rest_url, rest_auth, client_cert, root_cert,
               schema_file, visibility_topic, data_source,
               scene_data_schema_file=None):
    self.cert = client_cert
    self.root_cert = root_cert
    self.rewrite_all_time = rewrite_all_time
    self.regulate_cache = {}
    self.mqtt_auth = mqtt_auth

    self.schema_val = SchemaValidation(schema_file, is_multi_message=True)

    self.scene_data_schema_validator = None
    if scene_data_schema_file and Path(scene_data_schema_file).exists():
      try:
        self.scene_data_schema_validator = SchemaValidation(
          scene_data_schema_file, is_multi_message=False,
        )
        log.info(f"Scene-data schema validator initialized from {scene_data_schema_file}")
      except Exception as e:
        log.error(f"Failed to initialize scene-data schema validator: {e}")

    self.pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)
    self.pubsub.onConnect = self.onConnect
    self.pubsub.connect()

    self.cache_manager = CacheManager(
      data_source,
      rest_url,
      rest_auth,
      root_cert,
      scene_cls=AnalyticsScene,
    )

    self.visibility_topic = visibility_topic
    log.info(f"AnalyticsService: visibility on {self.visibility_topic} topic")
    return

  def loopForever(self):
    return self.pubsub.loopForever()

  # ------------------------------------------------------------------
  # Publication
  # ------------------------------------------------------------------

  def publishDetections(self, scene, objects, ts, otype, jdata, camera_id):
    if not hasattr(scene, 'lastPubCount'):
      scene.lastPubCount = {}
    if not hasattr(scene, 'last_published_detection'):
      scene.last_published_detection = defaultdict(lambda: None)
    self.publishRegulatedDetections(scene, objects, otype, jdata, camera_id)
    self.publishRegionDetections(scene, objects, otype, jdata)
    return

  def shouldPublish(self, last, now, max_delay):
    return last is None or now - last >= max_delay

  def calculateRate(self):
    now = get_epoch_time()
    if not hasattr(self, "regulate_rate"):
      self.regulate_last = now
      self.regulate_rate = 1
    delta = now - self.regulate_last
    self.regulate_rate *= AVG_FRAMES
    self.regulate_rate += delta
    self.regulate_rate /= AVG_FRAMES + 1
    self.regulate_last = now
    return self.regulate_rate

  def publishRegulatedDetections(self, scene_obj, msg_objects, otype, jdata, camera_id):
    update_rate = self.calculateRate()
    scene_uid = scene_obj.uid

    if scene_uid not in self.regulate_cache:
      self.regulate_cache[scene_uid] = {'objects': {}, 'rate': {}, 'last': None}
    scene = self.regulate_cache[scene_uid]

    scene['objects'][otype] = buildDetectionsList(
      msg_objects, scene_obj,
      self.visibility_topic == 'unregulated',
      include_sensors=True, include_region_dwell=True,
    )

    # Derive camera rate from object visibility (no single camera_id in analytics)
    if 'rate' in jdata:
      camera_ids = set()
      for obj in jdata.get('objects', []):
        camera_ids.update(obj.get('visibility', []))
      scene_rate = jdata['rate']
      configured_cameras = set(scene_obj.cameras.keys())
      for cam_id in camera_ids:
        if cam_id in configured_cameras:
          scene['rate'][cam_id] = scene_rate

    now = get_epoch_time()
    if self.shouldPublish(scene['last'], now, 1 / scene_obj.regulated_rate):
      objects = []
      is_regulated = self.visibility_topic == 'regulated'
      msg_objects_lookup = {obj.gid: obj for obj in msg_objects} if is_regulated else {}

      for key in scene['objects']:
        for obj in scene['objects'][key]:
          if is_regulated:
            aobj = msg_objects_lookup.get(obj['id'], None)
            if aobj is not None:
              computeCameraBounds(scene_obj, aobj, obj)
          objects.append(obj)

      new_jdata = {
        'timestamp': jdata['timestamp'],
        'objects': objects,
        'id': jdata['id'],
        'name': jdata['name'],
        'scene_rate': round(1 / update_rate, 1),
        'rate': scene['rate'],
      }
      jstr = orjson.dumps(new_jdata, option=orjson.OPT_SERIALIZE_NUMPY)
      self.pubsub.publish(PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid), jstr)
      scene['last'] = now
    return

  def publishRegionDetections(self, scene, objects, otype, jdata):
    current_time = get_epoch_time(jdata['timestamp'])
    for rname in scene.regions:
      robjects = [obj for obj in objects if rname in obj.chain_data.regions]
      region_objects = buildDetectionsList(
        robjects, scene, False,
        include_sensors=True, include_region_dwell=True,
        current_time=current_time,
      )
      olen = len(region_objects)
      rid = scene.name + "/" + rname + "/" + otype
      if olen > 0 or rid not in scene.lastPubCount or scene.lastPubCount[rid] > 0:
        region_jdata = dict(jdata)
        region_jdata['objects'] = region_objects
        jstr = orjson.dumps(region_jdata, option=orjson.OPT_SERIALIZE_NUMPY)
        self.pubsub.publish(
          PubSub.formatTopic(PubSub.DATA_REGION, scene_id=scene.uid,
                             region_id=rname, thing_type=otype),
          jstr,
        )
        scene.lastPubCount[rid] = olen
    return

  # ------------------------------------------------------------------
  # Message handlers
  # ------------------------------------------------------------------

  def handleSceneDataMessage(self, client, userdata, message):
    """Handle tracked-object messages from Tracker or Scene Controller."""
    topic = PubSub.parseTopic(message.topic)
    try:
      jdata = orjson.loads(message.payload.decode('utf-8'))
    except (orjson.JSONDecodeError, UnicodeDecodeError) as e:
      log.error(f"Invalid scene data payload on {message.topic}: {e}")
      return

    scene_id = topic['scene_id']
    detection_type = topic['thing_type']
    log.debug(f"Scene data: scene={scene_id}, type={detection_type}, "
              f"objects={len(jdata.get('objects', []))}")

    scene = self.cache_manager.sceneWithID(scene_id)
    if scene is None:
      log.warning(f"Unknown scene_id={scene_id}")
      return

    if self.scene_data_schema_validator is not None:
      if not self.scene_data_schema_validator.validate(jdata, check_format=True):
        log.error(f"Scene data validation failed for scene={scene_id}, type={detection_type}")
        return

    scene.updateTrackedObjects(detection_type, jdata.get('objects', []))
    analytics_objects = scene.getTrackedObjects(detection_type)
    msg_when = get_epoch_time(jdata.get('timestamp'))

    scene._updateEvents(detection_type, msg_when, analytics_objects,
                        publish_fn=self.pubsub.publish)
    scene._updateVisible(analytics_objects)
    self.publishDetections(scene, analytics_objects, msg_when, detection_type, jdata, None)
    return

  def handleSensorMessage(self, client, userdata, message):
    """Handle sensor data messages."""
    jdata = orjson.loads(message.payload.decode('utf-8'))

    if not self.schema_val.validateMessage("singleton", jdata, check_format=True):
      return

    sensor_id = jdata['id']
    scene = self.cache_manager.sceneWithSensorID(sensor_id)
    if scene is None:
      return

    if self.rewrite_all_time:
      ts = get_epoch_time()
      jdata['timestamp'] = get_iso_time(ts)
    else:
      ts = get_epoch_time(jdata['timestamp'])

    if not scene.processSensorData(jdata, when=ts):
      log.error("Sensor fail", sensor_id)
      self.cache_manager.invalidate()
      return

    jdata['scene_id'] = scene.uid
    jdata['scene_name'] = scene.name
    publish_events(scene, jdata['timestamp'], self.pubsub.publish)
    return

  def handleDatabaseMessage(self, client, userdata, message):
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      try:
        self.updateSubscriptions()
        self.updateRegulateCache()
      except Exception as e:
        log.warning("Failed to update database: %s", e)
    return

  # ------------------------------------------------------------------
  # MQTT lifecycle
  # ------------------------------------------------------------------

  def onConnect(self, client, userdata, flags, rc):
    log.info("Connected with result code", rc)
    if rc != 0:
      exit(1)
    self.subscribed = set()
    self.updateSubscriptions()
    self.pubsub.addCallback(PubSub.formatTopic(PubSub.CMD_DATABASE), self.handleDatabaseMessage)
    log.info("Subscribed to", PubSub.formatTopic(PubSub.CMD_DATABASE))
    return

  def updateSubscriptions(self):
    log.debug("UPDATE SUBSCRIPTIONS")
    self.cache_manager.invalidate()
    if not hasattr(self, 'subscribed'):
      self.subscribed = set()
    need_subscribe = set()

    self.scenes = self.cache_manager.allScenes()
    for scene in self.scenes:
      need_subscribe.add((
        PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene.uid, thing_type="+"),
        self.handleSceneDataMessage,
      ))
      for sensor in scene.sensors:
        need_subscribe.add((
          PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor),
          self.handleSensorMessage,
        ))

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

  def updateRegulateCache(self):
    scene_ids = {s.uid for s in self.scenes}
    for scene_id in list(self.regulate_cache.keys()):
      if scene_id not in scene_ids:
        self.regulate_cache.pop(scene_id)
    return
