#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
from http import HTTPStatus

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time, get_epoch_time

from tests.common_test_utils import check_event_contains_data
from tests.functional import FunctionalTest
from tests.utils.log import get_logger

ROI_NAME = "Automated_ROI"
FRAMES_PER_SECOND = 10
PERSON = "person"
REGION = "region"
MAX_CONTROLLER_WAIT = 30 # seconds
MAX_ATTEMPTS = 3

log = get_logger(__name__)

class SceneObjectMqtt(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneUID = self.params['scene_id']
    self.roiName = ROI_NAME
    self.frameRate = FRAMES_PER_SECOND
    self.roi_deleted = False
    self.message_received_after_delete = False
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    assert res, (res.errors)

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'], int(self.params['broker_port']))

    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def eventReceived(self, pahoClient, userdata, message):
    data = message.payload.decode("utf-8")
    regionData = json.loads(data)
    check_event_contains_data(regionData, "region")

    if getattr(self, "roi_deleted", False):
      self.message_received_after_delete = True
      log.warning("Event received after ROI deletion (unexpected)")
      return

    for regionObj in regionData['objects']:
      for sceneObj in self.sceneData['objects']:
        if regionObj['id'] == sceneObj['id']:
          self.expectedEnter.append(sceneObj['id'])
    self.verifyRegionEvent(regionData)
    return

  def regionDataReceived(self, pahoClient, userdata, message):
    region_data = json.loads(message.payload.decode("utf-8"))

    if getattr(self, "roi_deleted", False):
      self.message_received_after_delete = True
      log.warning("Region data received after ROI deletion (unexpected)")
      return

    objects = region_data.get('objects', [])
    if not objects:
      return

    self.regionDataNonEmptyCount += 1
    if self.object_in_region:
      region_ts = get_epoch_time(region_data['timestamp'])
      self.regionDataTimestampsWhileInside.append(region_ts)
    return

  def verifyRegionEvent(self, regionEvent):
    self.entered = False
    self.exited = False

    if len(regionEvent['entered']) > 0:
      for event in regionEvent['entered']:
        assert len(self.expectedEnter) > 0
        if event['id'] in self.expectedEnter:
          currPoint = event['translation']
          if self.isWithinRectangle(self.roiPoints[1], self.roiPoints[3], (currPoint[0], currPoint[1])):
            self.expectedExit.append(event['id'])
            self.expectedEnter.remove(event['id'])
            self.entered = True
            self.object_in_region = True
            # Track entry time for dwell verification
            if event['id'] not in self.objectEntryTimes:
              self.objectEntryTimes[event['id']] = get_epoch_time()
            log.info(f"object with id {event['id']} entered region")

    if len(regionEvent['exited']) > 0:
      for event in regionEvent['exited']:
        assert len(self.expectedExit) > 0
        if event['object']['id'] in self.expectedExit:
          self.expectedExit.remove(event['object']['id'])
          self.exited = True
          self.object_in_region = False
          log.info(f"object with id {event['object']['id']} exited region")
    return

  def verifyRegionDataUpdates(self):
    """Verify that DATA_REGION updates continue while object remains in region."""
    assert self.regionDataNonEmptyCount > 0, "Expected at least one non-empty DATA_REGION message"
    assert len(self.regionDataTimestampsWhileInside) >= 2, \
      "Expected repeated DATA_REGION updates while object is inside region"
    assert self.regionDataTimestampsWhileInside[-1] > self.regionDataTimestampsWhileInside[0], \
      "Expected DATA_REGION timestamps to advance across in-region updates"
    return

  def verifyRegionDataUpdates(self):
    """Verify that DATA_REGION updates continue while object remains in region."""
    assert self.regionDataNonEmptyCount > 0, "Expected at least one non-empty DATA_REGION message"
    assert len(self.regionDataTimestampsWhileInside) >= 2, \
      "Expected repeated DATA_REGION updates while object is inside region"
    assert self.regionDataTimestampsWhileInside[-1] > self.regionDataTimestampsWhileInside[0], \
      "Expected DATA_REGION timestamps to advance across in-region updates"
    return

  def isWithinRectangle(self, bl, tr, curr_point):
    if (curr_point[0] > bl[0] and curr_point[0] < tr[0] and \
      curr_point[1] > bl[1] and curr_point[1] < tr[1]):
      return True
    else:
      return False

  def setupROI(self, roiData):
    res = self.rest.createRegion(roiData)
    assert res.statusCode == HTTPStatus.CREATED, (res.statusCode, res.errors)

    self.roi_uid = res['uid']
    topic = PubSub.formatTopic(PubSub.EVENT, event_type="count", scene_id=self.sceneUID,
                               region_id=self.roi_uid, region_type=REGION)
    self.pubsub.addCallback(topic, self.eventReceived)

    data_topic = PubSub.formatTopic(PubSub.DATA_REGION, scene_id=self.sceneUID,
                    region_id=self.roi_uid, thing_type=PERSON)
    self.pubsub.addCallback(data_topic, self.regionDataReceived)

    assert res['points']
    return res['points']

  def deleteROI(self, roi_uid):
    res = self.rest.deleteRegion(roi_uid)
    assert res.statusCode == HTTPStatus.OK, (res.statusCode, res.errors)
    log.info(f"ROI {roi_uid} deleted successfully")
    self.roi_deleted = True
    return

  def sendDetections(self, objLocation, frame_rate):
    jdata = self.objData()
    for location in objLocation:
      camera_id = jdata['id']
      jdata['timestamp'] = get_iso_time()
      jdata['objects'][PERSON][0]['bounding_box']['y'] = location
      detection = json.dumps(jdata)
      self.pubsub.publish(PubSub.formatTopic(PubSub.DATA_CAMERA,
                                        camera_id=camera_id), detection)
      time.sleep(1 / frame_rate)
    return

  def runSceneObjMqttInitialize(self):
    self.expectedEnter = []
    self.expectedExit = []
    self.sceneData = None
    self.entered = False
    self.exited = False
    self.roiPoints = ((0.9, 4.0), (0.9, 2.4),
                      (8.1, 2.4), (8.1, 4.0))
    self.message_received_after_delete = False
    self.object_in_region = False
    self.regionDataNonEmptyCount = 0
    self.regionDataTimestampsWhileInside = []
    self.objectEntryTimes = {}  # Track when each object entered region for dwell verification
    self.previousDwellTimes = {}  # Track previous dwell times to verify monotonic increase
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    return

  def sceneReady(self, max_attempts, waitTopic, publishTopic, objData):
    attempts = 0
    ready = None

    while attempts < max_attempts:
      attempts += 1
      begin = get_epoch_time()
      ready = self.sceneControllerReady(waitTopic, publishTopic, MAX_CONTROLLER_WAIT,
                                      begin, 1 / self.frameRate, objData)
      if ready:
        break
    else:
      log.warning("reached max number of attempts to wait for scene controller")
    return

  def regulatedReceived(self, pahoClient, userdata, message):
    data = message.payload.decode("utf-8")
    self.sceneData = json.loads(data)
    # Track that dwell data appears in scene messages when expected
    self.verifyDwellPresenceInSceneData(self.sceneData)
    return

  def verifyDwellPresenceInSceneData(self, sceneData):
    """Verify dwell values appear in scene object data when objects are in regions.

    Unlike unit tests which validate calculation formulas, this checks integration:
    that dwell data is present and available in the scene data stream.
    """
    if 'objects' not in sceneData or not sceneData['objects']:
      return

    for obj in sceneData['objects']:
      obj_id = obj.get('id')
      if not obj_id or obj_id not in self.objectEntryTimes:
        continue

      current_regions = set((obj.get('regions') or {}).keys())

      # Reset dwell tracking for regions the object has left so that a
      # re-entry (dwell starting at 0) does not trigger a false decrease.
      for key in list(self.previousDwellTimes.keys()):
        if key[0] == obj_id and key[1] not in current_regions:
          del self.previousDwellTimes[key]

      # Check that dwell data is present for objects known to be in regions
      if 'regions' in obj and obj['regions']:
        for region_name, region_data in obj['regions'].items():
          if 'dwell' in region_data:
            dwell = region_data['dwell']
            # Basic sanity check: dwell should be non-negative
            assert dwell >= 0, f"Object {obj_id} has negative dwell: {dwell}"

            # Verify monotonic increase (no dwell decrease over time)
            key = (obj_id, region_name)
            if key in self.previousDwellTimes:
              prev_dwell = self.previousDwellTimes[key]
              assert dwell >= prev_dwell - 0.2, \
                f"Object {obj_id} dwell in {region_name} decreased from {prev_dwell:.2f} to {dwell:.2f}"

            self.previousDwellTimes[key] = dwell
    return

  def runSceneObjMqttPrepare(self):
    objData = self.objData()
    waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                   scene_id=self.sceneUID, thing_type=PERSON)
    publishTopic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=objData['id'])
    objLocation = self.getLocations()
    objData['objects'][PERSON][0]['bounding_box']['y'] = objLocation[0]
    self.sceneReady(MAX_ATTEMPTS, waitTopic, publishTopic, objData)

    self.getScene()
    roi = {'scene': self.sceneUID,
         'name': self.roiName,
         'points': self.roiPoints}

    points = self.setupROI(roi)

    topic_regulated = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.sceneUID)
    self.pubsub.addCallback(topic_regulated, self.regulatedReceived)

    log.info(f"BottomLeft: {points[1]}")
    log.info(f"TopRight: {points[3]}")
    return

  def runSceneObjMqttPrepareExtra(self):
    return

  def runROIMqttExecute(self):
    objLocation = self.getLocations()
    self.sendDetections(objLocation, self.frameRate)
    log.info(f"Expected entered list: {self.expectedEnter}")
    log.info(f"Expected exited list: {self.expectedExit}")
    return

  def runROIMqttDelete(self):
    self.deleteROI(self.roi_uid)
    objLocation = self.getLocations()
    self.sendDetections(objLocation, self.frameRate)
    time.sleep(2)
    return

  def runROIMqttVerifyPassed(self):
    if not (
      self.exited and self.entered == False
      and len(self.expectedExit) == 0
      and len(self.expectedEnter) == 0
    ):
      return False

    self.verifyRegionDataUpdates()
    return True

  def runROIMqttVerifyNoEventsAfterDelete(self):

    time.sleep(2)
    if self.message_received_after_delete:
      log.warning("Still receiving message from ROI!")
      return False
    log.info("No events published after ROI deletion")
    return True

  def runSceneObjMqttVerifyPassedExtra(self):
    return True

  def runSceneObjMqttFinally(self):
    self.pubsub.loopStop()
    self.recordTestResult()
    return
