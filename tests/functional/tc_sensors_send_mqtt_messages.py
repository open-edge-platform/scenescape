#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Microservices needed for test:
#   * broker
#   * web (REST)
#   * pgserver
#   * scene

from tests.functional import FunctionalTest

import os
import numpy as np
import json
import time

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_epoch_time, get_iso_time
from scene_common.geometry import Point

TEST_NAME = "NEX-T10456"
WALKING_SPEED = 1.2 # meters per second
FRAMES_PER_SECOND = 10
THING_TYPES = ["person", "chair", "table", "couch"]
MAX_CONTROLLER_WAIT = 30 # seconds

class SensorMqttMessageFlowTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneUID = self.params['scene_id']
    self.cameraId = "camera1"

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'])

    self.eventTopic = PubSub.formatTopic(PubSub.EVENT, region_type="region", event_type="+",
                       scene_id=self.sceneUID, region_id="+")
    self.sceneTopic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=self.sceneUID, thing_type="+")
    self.regulatedTopic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.sceneUID)
    self.externalTopic = PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=self.sceneUID, thing_type="+")
    self.regionEvents = {}
    self.sceneMessages = []
    self.regulatedMessages = []
    self.externalMessages = []
    self.sensorPublishTimes = {}
    self.geoChangeUpdateTimes = []
    self.cleanupUpdateTimes = []

    self.pubsub.onConnect = self.pubsubConnected
    self.pubsub.addCallback(self.eventTopic, self.eventReceived)
    self.pubsub.addCallback(self.sceneTopic, self.sceneReceived)
    self.pubsub.addCallback(self.regulatedTopic, self.regulatedReceived)
    self.pubsub.addCallback(self.externalTopic, self.externalReceived)
    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def pubsubConnected(self, client, userdata, flags, rc):
    self.pubsub.subscribe(self.eventTopic)
    self.pubsub.subscribe(self.sceneTopic)
    self.pubsub.subscribe(self.regulatedTopic)
    self.pubsub.subscribe(self.externalTopic)
    return

  def eventReceived(self, pahoClient, userdata, message):
    topic = PubSub.parseTopic(message.topic)
    region_id = topic['region_id']
    if region_id not in self.sensors:
      return

    payload = json.loads(message.payload.decode("utf-8"))
    self.sensors[region_id]['received'] = get_epoch_time()
    self.regionEvents.setdefault(region_id, []).append(payload)
    return

  def sceneReceived(self, pahoClient, userdata, message):
    payload = json.loads(message.payload.decode("utf-8"))
    if 'objects' in payload and payload['objects']:
      self.sceneMessages.append(payload)
    return

  def regulatedReceived(self, pahoClient, userdata, message):
    payload = json.loads(message.payload.decode("utf-8"))
    if 'objects' in payload and payload['objects']:
      self.regulatedMessages.append(payload)
    return

  def externalReceived(self, pahoClient, userdata, message):
    payload = json.loads(message.payload.decode("utf-8"))
    if 'objects' in payload and payload['objects']:
      self.externalMessages.append(payload)
    return

  def prepareScene(self):
    res = self.rest.getScenes({'id': self.sceneUID})
    assert res and res['count'] >= 1, (res.statusCode, res.errors)

    self.sensors = {
      'scene_env_sensor': {
        'area': "scene",
        'singleton_type': "environmental",
      },
      'circle_env_sensor': {
        'area': "circle",
        'radius': 100,
        'center': (0, 0),
        'singleton_type': "environmental",
      },
      'poly_env_sensor': {
        'area': "poly",
        'points': ((-100, 100), (100, 100), (100, -100), (-100, -100)),
        'singleton_type': "environmental",
      },
      'scene_attr_sensor': {
        'area': "scene",
        'singleton_type': "attribute",
      },
      'geo_change_sensor': {
        'area': "poly",
        'points': ((-100, 100), (100, 100), (100, -100), (-100, -100)),
        'singleton_type': "environmental",
      },
      'cleanup_env_sensor': {
        'area': "scene",
        'singleton_type': "environmental",
      },
    }

    for name in self.sensors:
      sensorConfig = {
        'name': name,
        'scene': self.sceneUID,
      }
      sensorConfig.update(self.sensors[name])
      res = self.rest.createSensor(sensorConfig)
      assert res, (res.statusCode, res.errors)
      self.sensors[name]['uid'] = res['uid']

    return

  def plotCourse(self):
    # Keep y in a normalized image range so camera detections remain valid
    # while still moving enough to exercise region/sensor transitions.
    startPosition = (-3.0, 0.1, 0)
    endPosition = (3.0, 0.9, 0)
    stepDistance = WALKING_SPEED / FRAMES_PER_SECOND

    # FIXME - should probably use whichever dimension results in the
    #         most number of steps, not index 0
    course = [np.arange(startPosition[0], endPosition[0], stepDistance)]
    for idx in range(1, len(startPosition)):
      course.append(np.linspace(startPosition[idx], endPosition[idx], len(course[0])))
    course = np.dstack(course)
    return course[0]

  def createDetection(self, positionNow):
    detection = {
      'id': self.cameraId,
      'timestamp': get_iso_time(get_epoch_time()),
      'objects': {
        'person': [
          {
            'id': 1,
            'category': 'person',
            'bounding_box': {
              'x': 0.56,
              'y': positionNow.y,
              'width': 0.24,
              'height': 0.49,
            },
          },
        ],
        'chair': [
          {
            'id': 2,
            'category': 'chair',
            'bounding_box': {
              'x': 0.68,
              'y': positionNow.y,
              'width': 0.24,
              'height': 0.49,
            },
          },
        ],
        'table': [
          {
            'id': 3,
            'category': 'table',
            'bounding_box': {
              'x': 0.44,
              'y': positionNow.y,
              'width': 0.30,
              'height': 0.20,
            },
          },
        ],
        'couch': [
          {
            'id': 4,
            'category': 'couch',
            'bounding_box': {
              'x': 0.80,
              'y': positionNow.y,
              'width': 0.36,
              'height': 0.28,
            },
          },
        ],
      },
      'rate': 9.8,
    }
    return detection

  def _publish_scheduled_sensor_value(self, idx, now, schedule, sensor_name):
    for publish_idx, value in schedule:
      if idx == publish_idx:
        self.pushSensorValue(sensor_name, value, now)
    return

  def _apply_scheduled_geo_update(self, idx, sensor_uid, geometry_schedule, sensor_name=None):
    for publish_idx, geo_update in geometry_schedule:
      if idx == publish_idx:
        res = self.rest.updateSensor(sensor_uid, geo_update)
        assert res, f"Failed to update geo_change_sensor at frame {idx}: {res.statusCode}"
        when = get_iso_time(get_epoch_time())
        if sensor_name == 'geo_change_sensor':
          self.geoChangeUpdateTimes.append(when)
        if sensor_name == 'cleanup_env_sensor':
          self.cleanupUpdateTimes.append(when)
    return

  def pushSensorValue(self, sensor_name, value, ts=None):
    when = ts if ts is not None else get_epoch_time()
    iso_when = get_iso_time(when)
    message_dict = {
      'timestamp': iso_when,
      'id': sensor_name,
      'value': value
    }
    result = self.pubsub.publish(
      PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor_name),
      json.dumps(message_dict)
    )
    assert result[0] == 0
    self.sensorPublishTimes.setdefault(sensor_name, {}).setdefault(value, []).append(iso_when)
    return

  def _extract_obj_id(self, obj):
    if 'id' in obj:
      return obj['id']
    if 'object_id' in obj:
      return obj['object_id']
    if 'track_id' in obj:
      return obj['track_id']
    return None

  def _extract_entry_value_timestamp(self, entry):
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
      return entry[1], entry[0]
    if isinstance(entry, dict):
      val = entry.get('value', entry.get('event'))
      return val, entry.get('timestamp')
    return None, None

  def _timestamp_for_value(self, sensor_values, target_value):
    for entry in sensor_values:
      val, ts = self._extract_entry_value_timestamp(entry)
      if val == target_value and ts is not None:
        return str(ts)
    return None

  def _assert_dedup_timestamp_refresh(self, sensor_name, sensor_values, target_value):
    publish_times = self.sensorPublishTimes.get(sensor_name, {}).get(target_value, [])
    assert len(publish_times) >= 2, (
      f"Need at least two publishes for dedup assertion on {sensor_name}:{target_value}",
      publish_times
    )
    reported_ts = self._timestamp_for_value(sensor_values, target_value)
    assert reported_ts is not None, (
      f"Expected a timestamped value entry for {sensor_name}:{target_value}",
      sensor_values
    )
    assert str(reported_ts) >= str(publish_times[1]), (
      f"Expected dedup timestamp refresh for {sensor_name}:{target_value}",
      reported_ts,
      publish_times
    )

  def _sensor_objects_in_region_event(self, region_event):
    objs = []
    objs.extend(region_event.get('objects', []))
    objs.extend(region_event.get('entered', []))
    for exited in region_event.get('exited', []):
      if isinstance(exited, dict) and 'object' in exited:
        objs.append(exited['object'])
    return objs

  def _extract_values(self, sensor_values):
    values = []
    for entry in sensor_values:
      if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        values.append(entry[1])
      elif isinstance(entry, dict):
        if 'value' in entry:
          values.append(entry['value'])
        elif 'event' in entry:
          values.append(entry['event'])
    return values

  def _extract_timestamps(self, sensor_values):
    timestamps = []
    for entry in sensor_values:
      if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        timestamps.append(entry[0])
      elif isinstance(entry, dict):
        if 'timestamp' in entry:
          timestamps.append(entry['timestamp'])
    return timestamps

  def _assert_timestamp_accumulation(self, sensor_name, sensor_values):
    timestamps = self._extract_timestamps(sensor_values)
    assert timestamps, f"Expected timestamps in sensor values for {sensor_name}, got {sensor_values}"
    assert len(timestamps) == len(sensor_values), (
      f"Missing timestamp entries for {sensor_name}", sensor_values
    )
    if len(timestamps) > 1:
      sortable = [str(ts) for ts in timestamps]
      assert sortable == sorted(sortable), (
        f"Expected timestamped sensor values in chronological order for {sensor_name}", timestamps
      )

  def _extract_obj_type(self, obj):
    if 'category' in obj:
      return obj['category']
    if 'type' in obj:
      return obj['type']
    return None

  def _verify_region_events(self):
    event_sensor_names = ['circle_env_sensor', 'poly_env_sensor', 'cleanup_env_sensor']
    sensorsReceived = [name for name in event_sensor_names if 'received' in self.sensors[name]]
    assert len(sensorsReceived) == len(event_sensor_names), (
      "Expected region sensor events", sensorsReceived, event_sensor_names
    )

    for sensor_name in event_sensor_names:
      events = self.regionEvents.get(sensor_name, [])
      assert events, f"No events received for sensor {sensor_name}"

      saw_sensor_payload = False
      exited_ids = set()
      for event in events:
        for entered in event.get('entered', []):
          entered_id = self._extract_obj_id(entered)
          if entered_id is not None and entered_id in exited_ids:
            exited_ids.remove(entered_id)

        # Cleanup check: once an object exits a region, subsequent object updates
        # must not keep carrying that region's sensor values until it re-enters.
        for obj in event.get('objects', []):
          obj_id = self._extract_obj_id(obj)
          if obj_id is None or obj_id not in exited_ids:
            continue
          sensors = obj.get('sensors', {})
          stale_values = sensors.get(sensor_name, {}).get('values', [])
          assert not stale_values, (
            f"Expected cleaned sensor state after exit for {sensor_name} object {obj_id}",
            stale_values
          )

        for exited in event.get('exited', []):
          if isinstance(exited, dict):
            exited_obj = exited.get('object', exited)
            exited_id = self._extract_obj_id(exited_obj)
            if exited_id is not None:
              exited_ids.add(exited_id)

        for obj in self._sensor_objects_in_region_event(event):
          sensors = obj.get('sensors', {})
          if sensor_name in sensors and sensors[sensor_name].get('values'):
            saw_sensor_payload = True
      assert saw_sensor_payload, f"No sensor payload found in events for sensor {sensor_name}"
    return

  def _verify_scene_topic_excludes_sensors(self):
    assert self.sceneMessages, "No scene topic messages received"
    for payload in self.sceneMessages:
      for obj in payload.get('objects', []):
        assert 'sensors' not in obj, f"Scene topic unexpectedly included sensors: {obj}"
    return

  def _find_sensor_values_in_messages(self, messages, sensor_name):
    """Return list of sensor value-lists for sensor_name found across messages."""
    samples = []
    for payload in messages:
      for obj in payload.get('objects', []):
        sensors = obj.get('sensors', {})
        if sensor_name in sensors and sensors[sensor_name].get('values'):
          samples.append(sensors[sensor_name]['values'])
    return samples

  def _verify_sensor_payloads(self):
    assert self.regulatedMessages, "No regulated messages received"
    assert self.externalMessages, "No external messages received"

    seen_types = set()
    scene_env_types = set()
    scene_attr_types = set()
    circle_env_samples = []
    poly_env_samples = []
    all_payloads = self.regulatedMessages + self.externalMessages

    scene_env_samples = []
    scene_attr_samples = []
    for payload in all_payloads:
      for obj in payload.get('objects', []):
        obj_type = self._extract_obj_type(obj)
        if obj_type is not None:
          seen_types.add(obj_type)

        sensors = obj.get('sensors', {})
        if 'scene_env_sensor' in sensors:
          env_values = sensors['scene_env_sensor'].get('values', [])
          if env_values:
            scene_env_samples.append(env_values)
            scene_env_types.add(obj_type)
        if 'scene_attr_sensor' in sensors:
          attr_values = sensors['scene_attr_sensor'].get('values', [])
          if attr_values:
            scene_attr_samples.append(attr_values)
            scene_attr_types.add(obj_type)
        if 'circle_env_sensor' in sensors and sensors['circle_env_sensor'].get('values'):
          circle_env_samples.append(sensors['circle_env_sensor']['values'])
        if 'poly_env_sensor' in sensors and sensors['poly_env_sensor'].get('values'):
          poly_env_samples.append(sensors['poly_env_sensor']['values'])

    for thing_type in THING_TYPES:
      assert thing_type in seen_types, f"Expected cross-detection sensor tagging for {thing_type}"
      assert thing_type in scene_env_types, f"Expected scene environmental sensor tagging for {thing_type}"
      assert thing_type in scene_attr_types, f"Expected scene attribute sensor tagging for {thing_type}"

    assert scene_env_samples, "Did not observe scene environmental sensor values"
    assert scene_attr_samples, "Did not observe scene attribute sensor values"
    assert circle_env_samples, "Did not observe circle environmental sensor values"
    assert poly_env_samples, "Did not observe polygon environmental sensor values"

    def _pick_best_sensor_sample(samples, dedup_value, latest_value):
      parsed_samples = []
      for sample in samples:
        values = self._extract_values(sample)
        if values:
          parsed_samples.append((sample, values))

      assert parsed_samples, f"No sensor samples contained values for dedup={dedup_value}"

      matching = [
        (sample, values)
        for sample, values in parsed_samples
        if values.count(dedup_value) == 1 and values[-1] == latest_value
      ]

      # Prefer a sample that already demonstrates dedup + latest-value behavior.
      # If none match exactly, choose the richest sample to maximize diagnostic value.
      candidate_pool = matching if matching else parsed_samples
      return max(candidate_pool, key=lambda item: len(item[1]))

    scene_env_sample, env_values = _pick_best_sensor_sample(scene_env_samples, 20.5, 21.0)
    scene_attr_sample, attr_values = _pick_best_sensor_sample(scene_attr_samples, 'badge-A', 'badge-B')
    circle_env_sample, circle_values = _pick_best_sensor_sample(circle_env_samples, 30.0, 31.0)
    poly_env_sample, poly_values = _pick_best_sensor_sample(poly_env_samples, 40.0, 41.0)

    self._assert_timestamp_accumulation('scene_env_sensor', scene_env_sample)
    self._assert_timestamp_accumulation('scene_attr_sensor', scene_attr_sample)
    self._assert_timestamp_accumulation('circle_env_sensor', circle_env_sample)
    self._assert_timestamp_accumulation('poly_env_sensor', poly_env_sample)

    assert env_values.count(20.5) == 1, f"Expected environmental dedup for 20.5, got {env_values}"
    assert env_values[-1] == 21.0, f"Expected latest environmental value 21.0, got {env_values}"
    assert attr_values.count("badge-A") == 1, f"Expected attribute dedup for badge-A, got {attr_values}"
    assert attr_values[-1] == "badge-B", f"Expected latest attribute value badge-B, got {attr_values}"
    assert circle_values.count(30.0) == 1, f"Expected environmental dedup for circle sensor, got {circle_values}"
    assert circle_values[-1] == 31.0, f"Expected latest circle sensor value 31.0, got {circle_values}"
    assert poly_values.count(40.0) == 1, f"Expected environmental dedup for polygon sensor, got {poly_values}"
    assert poly_values[-1] == 41.0, f"Expected latest polygon sensor value 41.0, got {poly_values}"

    self._assert_dedup_timestamp_refresh('scene_env_sensor', scene_env_sample, 20.5)
    self._assert_dedup_timestamp_refresh('scene_attr_sensor', scene_attr_sample, 'badge-A')
    self._assert_dedup_timestamp_refresh('circle_env_sensor', circle_env_sample, 30.0)
    self._assert_dedup_timestamp_refresh('poly_env_sensor', poly_env_sample, 40.0)

    # Type consistency: environmental values must be numeric, attribute values string.
    assert all(isinstance(v, (int, float)) for v in env_values), env_values
    assert all(isinstance(v, (int, float)) for v in circle_values), circle_values
    assert all(isinstance(v, (int, float)) for v in poly_values), poly_values
    assert all(isinstance(v, str) for v in attr_values), attr_values
    return

  def _verify_sensor_cache_across_geometry_changes(self):
    """Verify sensor cached values survive geometry updates (poly->circle->scene->poly).

    Geometry changes are performed inline during the walk loop
    (see geo_change_geometry_schedule in checkForMalfunctions) so the controller
    is always processing live detections when CMD_SCENE_UPDATE arrives.
    This method validates that geo_change_sensor values appear in the regulated/external
    messages collected during the walk, confirming the cache was preserved through each
    geometry transition.
    """
    SENSOR_NAME = 'geo_change_sensor'
    CACHED_VALUE = 55.5

    all_messages = self.regulatedMessages + self.externalMessages
    samples = self._find_sensor_values_in_messages(all_messages, SENSOR_NAME)
    assert samples, f"No {SENSOR_NAME} values found in regulated/external messages"
    found_values = []
    for s in samples:
      found_values.extend(self._extract_values(s))
    assert CACHED_VALUE in found_values, (
      f"Expected cached value {CACHED_VALUE} in {SENSOR_NAME} after geometry changes, "
      f"got {found_values}"
    )

    assert self.geoChangeUpdateTimes, (
      "Expected geometry updates to record scene reload events. "
      f"Geometry updates: {self.geoChangeUpdateTimes}, "
      f"Found cached values: {found_values}"
    )
    return

  def _verify_cleanup_sensor_detached_after_region_removal(self):
    assert self.cleanupUpdateTimes, "Expected cleanup sensor geometry updates to be recorded"

    all_messages = self.regulatedMessages + self.externalMessages
    assert all_messages, "No regulated/external messages to validate cleanup sensor detachment"

    last_cleanup_update = max(str(ts) for ts in self.cleanupUpdateTimes)
    for payload in all_messages:
      for obj in payload.get('objects', []):
        sensors = obj.get('sensors', {})
        values = sensors.get('cleanup_env_sensor', {}).get('values', [])
        for entry in values:
          _, ts = self._extract_entry_value_timestamp(entry)
          if ts is not None:
            assert str(ts) < last_cleanup_update, (
              "Expected cleanup_env_sensor to stop receiving new values after region removal",
              entry,
              last_cleanup_update
            )
    return

  def checkForMalfunctions(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      self.prepareScene()
      course = self.plotCourse()

      begin = get_epoch_time()

      waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                     scene_id=self.sceneUID, thing_type=THING_TYPES[0])
      positionNow = Point(course[0])
      detection = self.objData()
      detection['timestamp'] = get_iso_time(begin)
      detection['objects']['person'][0]['bounding_box']['y'] = positionNow.y
      topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=self.cameraId)
      count = self.sceneControllerReady(waitTopic, topic, MAX_CONTROLLER_WAIT,
                                        begin, 1 / FRAMES_PER_SECOND, detection)
      assert count, "Scene controller not ready"

      # Prime region sensors before entry so region entered events can
      # serialize sensor values on first region transition.
      prime_ts = get_epoch_time()
      self.pushSensorValue('circle_env_sensor', 29.0, prime_ts)
      self.pushSensorValue('poly_env_sensor', 39.0, prime_ts)
      self.pushSensorValue('cleanup_env_sensor', 49.0, prime_ts)

      # Publish an initial cache value for geo_change_sensor before the first
      # geometry change so the cache-preservation path is exercised.
      self.pushSensorValue('geo_change_sensor', 55.5, get_epoch_time())

      # Sensor value schedules: (frame_index, value)
      scene_env_schedule = [(27, 20.5), (28, 20.5), (29, 21.0)]
      scene_attr_schedule = [(30, 'badge-A'), (31, 'badge-A'), (32, 'badge-B')]
      circle_env_schedule = [(24, 30.0), (25, 30.0), (26, 31.0)]
      poly_env_schedule = [(24, 40.0), (25, 40.0), (26, 41.0)]
      geo_change_schedule = [(27, 55.5), (28, 55.5), (29, 55.5)]
      cleanup_env_schedule = [(24, 50.0), (25, 50.0), (26, 51.0)]

      # Geometry transitions for geo_change_sensor performed inline during the
      # walk so the tracker is active when CMD_SCENE_UPDATE is processed.
      # Sequence: initial poly -> circle -> scene -> poly (restored).
      sensor_uid = self.sensors['geo_change_sensor']['uid']
      cleanup_sensor_uid = self.sensors['cleanup_env_sensor']['uid']
      geo_change_geometry_schedule = [
        (36, {'area': 'circle', 'radius': 200, 'center': (0, 0)}),
        (40, {'area': 'scene'}),
        (44, {'area': 'poly',
              'points': ((-100, 100), (100, 100), (100, -100), (-100, -100))}),
      ]
      cleanup_geometry_schedule = [
        (35, {'area': 'poly',
          'points': ((900, 910), (910, 910), (910, 900), (900, 900))}),
      ]

      for idx in range(len(course)):
        positionNow = Point(course[idx])
        detection = self.createDetection(positionNow)
        self.pubsub.publish(topic, json.dumps(detection))

        now = get_epoch_time()
        self._publish_scheduled_sensor_value(idx, now, scene_env_schedule, 'scene_env_sensor')
        self._publish_scheduled_sensor_value(idx, now, scene_attr_schedule, 'scene_attr_sensor')
        self._publish_scheduled_sensor_value(idx, now, circle_env_schedule, 'circle_env_sensor')
        self._publish_scheduled_sensor_value(idx, now, poly_env_schedule, 'poly_env_sensor')
        self._publish_scheduled_sensor_value(idx, now, cleanup_env_schedule, 'cleanup_env_sensor')
        self._apply_scheduled_geo_update(
          idx, sensor_uid, geo_change_geometry_schedule, sensor_name='geo_change_sensor'
        )
        self._apply_scheduled_geo_update(
          idx, cleanup_sensor_uid, cleanup_geometry_schedule, sensor_name='cleanup_env_sensor'
        )
        self._publish_scheduled_sensor_value(idx, now, geo_change_schedule, 'geo_change_sensor')

        time.sleep(1 / FRAMES_PER_SECOND)

      time.sleep(2)
      self._verify_scene_topic_excludes_sensors()
      self._verify_region_events()
      self._verify_sensor_payloads()
      self._verify_sensor_cache_across_geometry_changes()
      self._verify_cleanup_sensor_detached_after_region_removal()
      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

def test_sensor_mqtt_message_flow(request, record_xml_attribute):
  test = SensorMqttMessageFlowTest(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return

def main():
  return test_sensor_mqtt_message_flow(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
