# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from pathlib import Path
import threading
import time

import orjson

from analytics.adapters.scene_model import AnalyticsScene
from analytics.event_publisher import publish_events, publish_potential_events
from analytics.prediction import PredictionManager
from scene_common.cache_manager import CacheManager
from scene_common.detections_builder import buildDetectionsList, computeCameraBounds
from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation
from scene_common.timestamp import get_epoch_time, get_iso_time

AVG_FRAMES = 100


class AnalyticsService:
  """MQTT controller for the standalone analytics service.

  Successor to Controller-proper scene analytics (regions, tripwires, sensors,
  regulated publish). Consumes tracked objects over MQTT instead of an
  in-process tracker. Tracker, Re-ID, pose-adjustment, NTP, and camera-data
  paths are not included. Instantiate and call loopForever() to run.
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
    self._publish_lock = threading.Lock()
    self._publish_owner = None

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
    self._prediction_pubsub = self.pubsub
    self._prediction_pubsub_is_dedicated = False

    self.cache_manager = CacheManager(
      data_source,
      rest_url,
      rest_auth,
      root_cert,
      scene_cls=AnalyticsScene,
    )

    self.visibility_topic = visibility_topic
    self.scenes = []
    self._prediction_manager = PredictionManager()
    self._prediction_lock = threading.RLock()
    self._prediction_stop = threading.Event()
    self._prediction_thread = None
    self._prediction_last_published = {}
    log.info(f"AnalyticsService: visibility on {self.visibility_topic} topic")
    return

  def loopForever(self):
    self._ensurePredictionRuntime()
    self.pubsub.loopStart()
    try:
      self._predictionLoop()
    finally:
      self._prediction_stop.set()
      self.pubsub.disconnect()
      self.pubsub.loopStop()

  def _ensurePredictionRuntime(self):
    """Initialize prediction collaborators for normal and test construction."""
    if not hasattr(self, '_prediction_manager'):
      self._prediction_manager = PredictionManager()
    if not hasattr(self, '_prediction_lock'):
      self._prediction_lock = threading.RLock()
    if not hasattr(self, '_prediction_stop'):
      self._prediction_stop = threading.Event()
    if not hasattr(self, '_prediction_thread'):
      self._prediction_thread = None
    if not hasattr(self, '_prediction_last_published'):
      self._prediction_last_published = {}
    if not hasattr(self, '_publish_lock'):
      self._publish_lock = threading.Lock()
    if not hasattr(self, '_publish_owner'):
      self._publish_owner = None
    if not hasattr(self, '_prediction_pubsub'):
      self._prediction_pubsub = self.pubsub
      self._prediction_pubsub_is_dedicated = False

  def _predictionLoop(self):
    """Publish due extrapolated snapshots until the MQTT loop exits."""
    while not self._prediction_stop.wait(0.01):
      self._predictionTick(get_epoch_time())

  def _predictionTick(self, now):
    """Process one scheduler tick for all scenes with live baselines."""
    self._ensurePredictionRuntime()
    with self._prediction_lock:
      for scene_id in self._prediction_manager.scene_ids():
        scene = self.cache_manager.sceneWithID(scene_id)
        if scene is None:
          events = self._prediction_manager.discard_scene(scene_id, now)
          publish_potential_events(None, events, self._publishPrediction)
          self.regulate_cache.pop(scene_id, None)
          continue
        result = self._prediction_manager.predict(scene, now)
        publish_potential_events(scene, result.events, self._publishPrediction)
        if not result.samples:
          continue
        cached = self.regulate_cache.get(scene_id)
        if cached is None:
          continue
        self._publishRegulatedSnapshot(
          scene, cached, now, predicted_samples=result.samples)
        cached['last_prediction'] = now

  # ------------------------------------------------------------------
  # Publication
  # ------------------------------------------------------------------

  def _publish(self, topic, payload, qos=0, retain=False):
    """Serialize outbound MQTT writes from callbacks and prediction ticks."""
    self._ensurePredictionRuntime()
    thread_name = threading.current_thread().name
    self._publish_lock.acquire()
    try:
      self._publish_owner = thread_name
      return self.pubsub.publish(topic, payload, qos=qos, retain=retain)
    finally:
      self._publish_owner = None
      self._publish_lock.release()

  def _publishPrediction(self, topic, payload, qos=0, retain=False):
    """Publish background prediction output on the shared MQTT client."""
    return self._publish(topic, payload, qos=qos, retain=retain)

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
    self._ensurePredictionRuntime()
    with self._prediction_lock:
      self._cacheRegulatedDetections(
        scene_obj, msg_objects, otype, jdata, camera_id)
    return

  def _cacheRegulatedDetections(self, scene_obj, msg_objects, otype, jdata, camera_id):
    update_rate = self.calculateRate()
    scene_uid = scene_obj.uid

    if scene_uid not in self.regulate_cache:
      self.regulate_cache[scene_uid] = {
        'objects': {},
        'rate': {},
        'last': None,
        'last_prediction': None,
        'id': jdata.get('id', scene_uid),
        'name': jdata.get('name', getattr(scene_obj, 'name', scene_uid)),
        'timestamp': jdata.get('timestamp'),
        'scene_rate': 0.0,
      }
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
    prediction_result = self._prediction_manager.predict(scene_obj, now)
    publish_potential_events(
      scene_obj, prediction_result.events, self._publish)
    max_delay = 1 / float(scene_obj.regulated_rate)
    # A real observation must immediately replace a displayed prediction.
    # Otherwise the regulated rate limit can leave the UI showing a dashed
    # extrapolation past the observed corner until the next allowed publish.
    replacing_prediction = scene['last_prediction'] is not None
    regulated_due = self.shouldPublish(scene['last'], now, max_delay)
    if replacing_prediction or regulated_due:
      is_regulated = self.visibility_topic == 'regulated'
      if is_regulated:
        msg_objects_lookup = {obj.gid: obj for obj in msg_objects}
        for obj in scene['objects'][otype]:
          aobj = msg_objects_lookup.get(obj['id'])
          if aobj is not None:
            computeCameraBounds(scene_obj, aobj, obj)
      scene['id'] = jdata.get('id', scene_uid)
      scene['name'] = jdata.get('name', getattr(scene_obj, 'name', scene_uid))
      scene['timestamp'] = jdata.get('timestamp')
      scene['scene_rate'] = round(1 / update_rate, 1)
      self._publishRegulatedSnapshot(
        scene_obj, scene, now,
        predicted_samples=prediction_result.samples)
      scene['last_prediction'] = now if prediction_result.samples else None
    return

  def _publishRegulatedSnapshot(
      self, scene_obj, cached, now, predicted_samples=None):
    """Publish an immutable observed/predicted copy of the regulated cache."""
    predictions = {
      (sample.detection_type, sample.object_id): sample
      for sample in (predicted_samples or [])
    }
    objects = []
    for detection_type, cached_objects in cached['objects'].items():
      for cached_object in cached_objects:
        obj = dict(cached_object)
        sample = predictions.get((detection_type, obj['id']))
        if sample is not None:
          obj['translation'] = sample.location.asCartesianVector
          obj['velocity'] = sample.velocity.asCartesianVector
          obj['position_source'] = 'predicted'
          obj['observation_timestamp'] = get_iso_time(
            sample.observation_timestamp)
          obj['prediction_age_ms'] = sample.prediction_age_ms
          obj['prediction_horizon_ms'] = sample.prediction_horizon_ms
        objects.append(obj)

    payload = {
      'timestamp': (
        get_iso_time(now) if predicted_samples else cached['timestamp']
      ),
      'objects': objects,
      'id': cached['id'],
      'name': cached['name'],
      'scene_rate': cached['scene_rate'],
      'rate': cached['rate'],
    }
    if predicted_samples:
      self._publishPrediction(
        PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_obj.uid),
        orjson.dumps(payload, option=orjson.OPT_SERIALIZE_NUMPY),
      )
    else:
      self._publish(
        PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_obj.uid),
        orjson.dumps(payload, option=orjson.OPT_SERIALIZE_NUMPY),
      )
    cached['last'] = now

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
        self._publish(
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

    self._ensurePredictionRuntime()
    with self._prediction_lock:
      scene.updateTrackedObjects(detection_type, jdata.get('objects', []))
      analytics_objects = scene.getTrackedObjects(detection_type)
      msg_when = get_epoch_time(jdata.get('timestamp'))
      prediction_when = get_epoch_time()
      for obj in analytics_objects:
        if getattr(obj, 'observation_timestamp', None) is None:
          obj.observation_timestamp = jdata.get('timestamp')
        obj.observation_is_fresh = (
          self._prediction_manager.is_fresh_observation(
            scene.uid, detection_type, obj, prediction_when,
            scheduling_timestamp=prediction_when)
        )

      # Prefer producer-supplied visibility; fill gaps before events so event
      # payloads and regulated output share the same camera ID lists.
      scene._updateVisible(analytics_objects)
      potential_events = self._prediction_manager.observe(
        scene, detection_type, analytics_objects, msg_when,
        scheduling_timestamp=prediction_when)
    publish_potential_events(scene, potential_events, self._publish)
    scene._updateEvents(detection_type, msg_when, analytics_objects,
                        publish_fn=self._publish)
    self.publishDetections(
      scene, analytics_objects, msg_when, detection_type, jdata, None)
    return

  def handleSensorMessage(self, client, userdata, message):
    """Handle sensor data messages."""
    try:
      jdata = orjson.loads(message.payload.decode('utf-8'))
    except (orjson.JSONDecodeError, UnicodeDecodeError) as e:
      log.error(f"Invalid sensor payload on {message.topic}: {e}")
      return

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
    publish_events(scene, jdata['timestamp'], self._publish)
    return

  def _publishRetainedCatalog(self, topic_id, scene_id, payload):
    """Publish *payload* as the last-known catalog for *scene_id* (retained)."""
    topic = PubSub.formatTopic(topic_id, scene_id=scene_id)
    self._publish(
      topic, orjson.dumps(payload).decode('utf-8'), qos=1, retain=True)
    return topic

  def publishTripwiresForScene(self, scene):
    """Publish the current tripwire catalog for *scene* as retained state."""
    result = self.cache_manager.data_source.getTripwires({'scene': scene.uid})
    if result.errors:
      log.warning(f"Failed to fetch tripwires for scene {scene.uid}: {result.errors}")
      return
    tripwires = [
      {'title': t.get('name', ''), 'uuid': t.get('uid', ''), 'points': t.get('points', [])}
      for t in result.get('results', [])
    ]
    topic = self._publishRetainedCatalog(
      PubSub.DATA_CHILD_TRIPWIRES, scene.uid, tripwires)
    log.debug(f"Published {len(tripwires)} tripwire(s) for scene {scene.uid} on {topic}")
    return

  def publishRoisForScene(self, scene):
    """Publish the current ROI catalog for *scene* as retained state."""
    result = self.cache_manager.data_source.getRegions({'scene': scene.uid})
    if result.errors:
      log.warning(f"Failed to fetch rois for scene {scene.uid}: {result.errors}")
      return
    rois = []
    for region in result.get('results', []):
      color_ranges = region.get('color_ranges') or {}

      rois.append({
        'title': region.get('name', ''),
        'uuid': region.get('uid', ''),
        'points': region.get('points', []),
        'volumetric': region.get('volumetric', False),
        'height': region.get('height', 1),
        'buffer_size': region.get('buffer_size', 0),
        'sectors': {
          'thresholds': color_ranges.get('sectors', []),
          'range_max': color_ranges.get('range_max', 0),
        },
      })
    topic = self._publishRetainedCatalog(PubSub.DATA_CHILD_ROIS, scene.uid, rois)
    log.debug(f"Published {len(rois)} roi(s) for scene {scene.uid} on {topic}")
    return

  def publishSensorsForScene(self, scene):
    """Publish the current generic sensor catalog for *scene* as retained state."""
    result = self.cache_manager.data_source.getSensors({'scene': scene.uid})
    if result.errors:
      log.warning(f"Failed to fetch sensors for scene {scene.uid}: {result.errors}")
      return

    sensors = []
    for sensor in result.get('results', []):
      center = sensor.get('center') or [None, None]
      color_ranges = sensor.get('color_ranges') or {}
      sensors.append({
        'title': sensor.get('name', ''),
        'uuid': sensor.get('uid') or sensor.get('sensor_id', ''),
        'area': sensor.get('area'),
        'radius': sensor.get('radius'),
        'x': center[0] if len(center) > 0 else None,
        'y': center[1] if len(center) > 1 else None,
        'points': sensor.get('points', []),
        'sectors': {
          'thresholds': color_ranges.get('sectors', []),
          'range_max': color_ranges.get('range_max', 0),
        },
        'singleton_type': sensor.get('singleton_type'),
      })

    topic = self._publishRetainedCatalog(PubSub.DATA_CHILD_SENSORS, scene.uid, sensors)
    log.debug(f"Published {len(sensors)} sensor(s) for scene {scene.uid} on {topic}")
    return

  def clearCatalogForScene(self, scene_id):
    """Overwrite retained catalogs so a removed scene does not leave stale state."""
    self._publishRetainedCatalog(PubSub.DATA_CHILD_TRIPWIRES, scene_id, [])
    self._publishRetainedCatalog(PubSub.DATA_CHILD_ROIS, scene_id, [])
    self._publishRetainedCatalog(PubSub.DATA_CHILD_SENSORS, scene_id, [])
    log.debug(f"Cleared retained analytics catalog for scene {scene_id}")
    return

  def handleDatabaseMessage(self, client, userdata, message):
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      try:
        self._ensurePredictionRuntime()
        with self._prediction_lock:
          self.updateSubscriptions()
          self.updateRegulateCache()
        for scene in getattr(self, 'scenes', []):
          self.publishTripwiresForScene(scene)
          self.publishRoisForScene(scene)
          self.publishSensorsForScene(scene)
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
    for scene in getattr(self, 'scenes', []):
      self.publishTripwiresForScene(scene)
      self.publishRoisForScene(scene)
      self.publishSensorsForScene(scene)
    return

  def updateSubscriptions(self):
    log.debug("UPDATE SUBSCRIPTIONS")
    self.cache_manager.invalidate()
    if not hasattr(self, 'subscribed'):
      self.subscribed = set()
    need_subscribe = set()

    previous_ids = {str(s.uid) for s in getattr(self, 'scenes', [])}
    self.scenes = self.cache_manager.allScenes()
    current_ids = {str(s.uid) for s in self.scenes}
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
    for scene_id in previous_ids - current_ids:
      self.clearCatalogForScene(scene_id)
    return

  def updateRegulateCache(self):
    self._ensurePredictionRuntime()
    with self._prediction_lock:
      scene_ids = {s.uid for s in self.scenes}
      for scene_id in list(self.regulate_cache.keys()):
        if scene_id not in scene_ids:
          self.regulate_cache.pop(scene_id, None)
    return
