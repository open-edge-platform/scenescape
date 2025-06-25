# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os
from collections import defaultdict

import ntplib

from controller.cache_manager import CacheManager
from controller.child_scene_controller import ChildSceneController
from controller.detections_builder import (buildDetectionsDict,
                                           buildDetectionsList,
                                           computeCameraBounds)
from controller.scene import Scene
from scene_common import log
from scene_common.geometry import Point, Region, Tripwire
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation
from scene_common.timestamp import adjust_time, get_epoch_time, get_iso_time
from scene_common.transform import applyChildTransform

AVG_FRAMES = 100

class SceneController:

  def __init__(self, rewrite_bad_time, rewrite_all_time, max_lag, mqtt_broker,
               mqtt_auth, rest_url, rest_auth, client_cert, root_cert, ntp_server,
               tracker_config_file, schema_file, visibility_topic):
    self.cert = client_cert
    self.root_cert = root_cert
    self.rewrite_bad_time = rewrite_bad_time
    self.rewrite_all_time = rewrite_all_time
    self.max_lag = max_lag
    self.regulate_cache = {}
    self.broker = mqtt_broker
    self.mqtt_auth = mqtt_auth
    self.tracker_config_data = {}
    self.tracker_config_file = tracker_config_file
    if tracker_config_file is not None:
      self.extractTrackerConfigData(tracker_config_file)

    self.last_time_sync = None
    self.ntp_server = ntp_server
    self.ntp_client = ntplib.NTPClient()
    self.time_offset = 0

    self.schema_val = SchemaValidation(schema_file)

    self.pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)
    self.pubsub.onConnect = self.onConnect
    self.pubsub.connect()

    self.cache_manager = CacheManager(rest_url, rest_auth, root_cert, self.tracker_config_data)

    self.visibility_topic = visibility_topic
    log.info(f"Publishing camera visibility info on ${self.visibility_topic} topic.")
    return

  def extractTrackerConfigData(self, tracker_config_file):
    if not os.path.exists(tracker_config_file) and not os.path.isabs(tracker_config_file):
      script = os.path.realpath(__file__)
      tracker_config_file = os.path.join(os.path.dirname(script), tracker_config_file)
    with open(tracker_config_file) as json_file:
      tracker_config = json.load(json_file)
      self.tracker_config_data["max_unreliable_time"] = tracker_config["max_unreliable_frames"]/tracker_config["baseline_frame_rate"]
      self.tracker_config_data["non_measurement_time_dynamic"] = tracker_config["non_measurement_frames_dynamic"]/tracker_config["baseline_frame_rate"]
      self.tracker_config_data["non_measurement_time_static"] = tracker_config["non_measurement_frames_static"]/tracker_config["baseline_frame_rate"]
    return

  def loopForever(self):
    return self.pubsub.loopForever()

  def publishDetections(self, scene, objects, ts, otype, jdata, camera_id):
    if not hasattr(scene, 'lastPubCount'):
      scene.lastPubCount = {}

    if not hasattr(scene, 'last_published_detection'):
      scene.last_published_detection = defaultdict(lambda: None)

    self.publishSceneDetections(scene, objects, otype, jdata)
    self.publishRegulatedDetections(scene, objects, otype, jdata, camera_id)
    self.publishRegionDetections(scene, objects, otype, jdata)
    return

  def shouldPublish(self, last, now, max_delay):
    return last is None or now - last >= max_delay

  def publishSceneDetections(self, scene, objects, otype, jdata):
    jdata['objects'] = buildDetectionsList(objects, scene, self.visibility_topic == 'unregulated')
    olen = len(jdata['objects'])
    cid = scene.name + "/" + otype
    if olen > 0 or cid not in scene.lastPubCount or scene.lastPubCount[cid] > 0:
      if 'debug_hmo_start_time' in jdata:
        jdata['debug_hmo_processing_time'] = get_epoch_time() - jdata['debug_hmo_start_time']
      jstr = json.dumps(jdata)
      new_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene.uid,
                                     thing_type=otype)
      self.pubsub.publish(new_topic, jstr)
      self.publishExternalDetections(scene, otype, jstr)
      scene.lastPubCount[cid] = olen
    return

  def publishExternalDetections(self, scene, otype, jstr):
    now = get_epoch_time()
    if self.shouldPublish(scene.last_published_detection[otype], now, 1/scene.external_update_rate):
      scene.last_published_detection[otype] = get_epoch_time()
      scene_hierarchy_topic = PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=scene.uid,
                                                 thing_type=otype)
      self.pubsub.publish(scene_hierarchy_topic, jstr)
    return

  def publishRegulatedDetections(self, scene_obj, msg_objects, otype, jdata, camera_id):
    update_rate = self.calculateRate()
    scene_uid = scene_obj.uid

    if scene_uid not in self.regulate_cache:
      self.regulate_cache[scene_uid] = {
        'objects': {},
        'rate': {},
        'last': None
      }
    scene = self.regulate_cache[scene_uid]
    scene['objects'][otype] = jdata['objects']
    if camera_id is not None:
      scene['rate'][camera_id] = jdata.get('rate', None)

    now = get_epoch_time()
    if self.shouldPublish(scene['last'], now, 1/scene_obj.regulated_rate):
      # If we're doing Regulated visibility, then we need to compute for all
      # the objects in the cache
      objects = []
      for key in scene['objects']:
        for obj in scene['objects'][key]:
          if self.visibility_topic == 'regulated':
            aobj = next((x for x in msg_objects if x.gid == obj['id']), None)
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
      jstr = json.dumps(new_jdata)
      topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
      self.pubsub.publish(topic, jstr)
      scene['last'] = now

    return

  def publishRegionDetections(self, scene, objects, otype, jdata):
    for rname in scene.regions:
      robjects = []
      for obj in objects:
        if rname in obj.chain_data.regions:
          robjects.append(obj)
      jdata['objects'] = buildDetectionsList(robjects, scene)
      olen = len(jdata['objects'])
      rid = scene.name + "/" + rname + "/" + otype
      if olen > 0 or rid not in scene.lastPubCount or scene.lastPubCount[rid] > 0:
        jstr = json.dumps(jdata)
        new_topic = PubSub.formatTopic(PubSub.DATA_REGION, scene_id=scene.uid,
                                       region_id=rname, thing_type=otype)
        self.pubsub.publish(new_topic, jstr)
        scene.lastPubCount[rid] = olen
    return

  def publishEvents(self, scene, ts_str):
    for event_type in scene.events:
      for _, region in scene.events[event_type]:
        etype = None
        metadata = None

        if isinstance(region, Tripwire):
          etype = 'tripwire'
          metadata = region.serialize()

        elif isinstance(region, Region):
          etype = 'region'
          metadata = region.serialize()
          metadata['fromSensor'] = (region.singleton_type != None)

        event_data = {
          'timestamp': ts_str,
          'scene_id': scene.uid,
          'scene_name': scene.name,
          etype + '_id': region.uuid,
          etype + '_name': region.name,
        }
        detections_dict, num_objects = self._buildAllRegionObjsList(scene, region, event_data)
        self._buildEnteredObjsList(region, event_data, detections_dict)
        self._buildExitedObjsList(scene, region, event_data)

        log.debug("EVENT DATA", event_data)
        if hasattr(region, 'value'):
          event_data['value'] = region.value
        event_data['metadata'] = metadata
        if not isinstance(region, Tripwire) or num_objects > 0:
          event_topic = PubSub.formatTopic(PubSub.EVENT,
                                           region_type=etype, event_type=event_type,
                                           scene_id=scene.uid, region_id=region.uuid)
          self.pubsub.publish(event_topic, json.dumps(event_data))

    self._clearSensorValuesOnExit(scene)

    return

  def _buildAllRegionObjsList(self, scene, region, event_data):
    counts = {}
    num_objects = 0
    all_objects = []
    for otype, objects in region.objects.items():
      counts[otype] = len(objects)
      num_objects += counts[otype]
      all_objects += objects
    event_data['counts'] = counts
    detections_dict = buildDetectionsDict(all_objects, scene)
    event_data['objects'] = list(detections_dict.values())
    return detections_dict, num_objects

  def _buildEnteredObjsList(self, region, event_data, detections_dict):
    entered = getattr(region, 'entered', {})
    event_data['entered'] = []
    for entered_list in entered.values():
      for item in entered_list:
        entered_obj = detections_dict[item.gid]
        event_data['entered'].extend([entered_obj])

  def _buildExitedObjsList(self, scene, region, event_data):
    exited = getattr(region, 'exited', {})
    event_data['exited'] = []
    exited_dict = {}
    for exited_list in exited.values():
      exited_objs = []
      for exited_obj, dwell in exited_list:
        exited_dict[exited_obj.gid] = dwell
        exited_objs.extend([exited_obj])
      exited_objs = buildDetectionsList(exited_objs, scene)
      exited_data = [{'object': exited_obj, 'dwell': exited_dict[exited_obj['id']]} for exited_obj in exited_objs]
      event_data['exited'].extend(exited_data)
    return

  def _clearSensorValuesOnExit(self, scene):
    """Clears the environmental sensor values accumulated by the exiting object"""
    for event_type in scene.events:
      for region_name, region in scene.events[event_type]:
        if hasattr(region, 'exited'):
          for detectionType in region.exited:
            for exit_data in region.exited[detectionType]:
              obj = exit_data[0]
              if region.singleton_type == "environmental":
                obj.chain_data.sensors.pop(region_name, None)
        region.exited = {}
        region.entered = {}
    return

  # Message handling
  def handleSensorMessage(self, client, userdata, message):
    """
    Handle a sensor message such as this
    MQTT Topic: scenescape/data/sensor/02:42:ac:11:00:05.1
        {"timestamp": "2018-09-12T19:03:49.600z",
         "subtype": "humidity",
         "value": "21.7",
         "id": "02:42:ac:11:00:05.1",
         "status": "green" }
    """
    message = message.payload.decode('utf-8')
    jdata = json.loads(message)

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

    self.publishEvents(scene, jdata['timestamp'])
    return

  def handleMovingObjectMessage(self, client, userdata, message):
    topic = PubSub.parseTopic(message.topic)
    jdata = json.loads(message.payload.decode('utf-8'))
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
        log.warn("{} FELL BEHIND by {}. SKIPPING {}".format(message.topic, lag, jdata['id']))
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
      self.publishEvents(scene, jdata['timestamp'])
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

  def updateRegulateCache(self):
    for scene in list(self.regulate_cache.keys()):
      if scene not in self.scenes:
        self.regulate_cache.pop(scene)
      else:
        for cam in scene['rate']:
          if cam not in scene.cameras:
            scene['rate'].pop(cam)
    return

  def handleDatabaseMessage(self, client, userdata, message):
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      self.updateSubscriptions()
      self.updateObjectClasses()
      self.updateCameras()
      self.updateRegulateCache()
    return

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

  # MQTT callbacks
  def onConnect(self, client, userdata, flags, rc):
    log.info("Connected with result code", rc)
    if rc != 0:
      exit(1)
    self.subscribed = set()
    self.updateSubscriptions()
    self.updateObjectClasses()
    topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
    self.pubsub.addCallback(topic, self.handleDatabaseMessage)
    log.info("Subscribed to", topic)
    # FIXME - update subscriptions when scenes/sensors/children added/deleted/renamed
    return

  def updateObjectClasses(self):
    results = self.cache_manager.getAssets()
    if results and 'results' in results:
      for scene in self.scenes:
        scene.tracker.updateObjectClasses(results['results'])
    return

  def republishEvents(self, client, userdata, message):
    """
    Republishes the child analytics under parent topic that
    enables parent to visualize them.
    """
    topic = PubSub.parseTopic(message.topic)
    msg = json.loads(message.payload.decode('utf-8'))

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
    self.pubsub.publish(event_topic, json.dumps(msg))
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
      for sensor in scene.sensors:
        need_subscribe.add((PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor),
                            self.handleSensorMessage))
      if hasattr(scene, 'children'):
        child_scenes = self.cache_manager.getChildScenes(scene.uid)

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
            need_subscribe.add((PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_name=info['name']), child_obj.publishStatus))

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
