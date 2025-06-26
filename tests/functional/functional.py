# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from tests.diagnostic import Diagnostic
import numpy as np
import threading
import json
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time, get_epoch_time
from scene_common import log

class FunctionalTest(Diagnostic):
  def buildArgparser(self):
    parser = self.argumentParser()
    parser.add_argument("--user", required=True, help="user to log into web server")
    parser.add_argument("--password", required=True, help="password to log into web server")
    parser.add_argument("--auth", default="/run/secrets/percebro.auth",
                        help="user:password or JSON file for MQTT authentication")
    parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                        help="path to ca certificate")
    parser.add_argument("--broker_url", default="broker.scenescape.intel.com",
                        help="hostname or IP of the broker")
    parser.add_argument("--broker_port", default=1883, help="broker port")
    parser.add_argument("--weburl", default="https://web.scenescape.intel.com",
                        help="Web URL of the server")
    parser.add_argument("--resturl", default="https://web.scenescape.intel.com/api/v1",
                        help="URL of REST server")
    parser.add_argument("--scene", default="Demo", help="name of scene to test against")
    parser.add_argument("--scene_id", default="3bc091c7-e449-46a0-9540-29c499bca18c", help="id of scene to test against")
    return parser

  def _trackingReceived(self, pahoClient, userdata, message):
    data = json.loads(message.payload.decode('utf-8'))
    if data is not None:
      log.debug("Tracking received", message.topic, data)
      self._sceneReadyCondition.acquire()
      self._sceneReadyCondition.notify()
      self._sceneReadyCondition.release()
    return

  def sceneControllerReady(self, waitTopic, publishTopic, timeout,
                           beginEpoch, interval, detection):
    """Keeps publishing `detection` to `publishTopic` until tracking
       information is received on `waitTopic` or timeout is
       reached. Updates timestamp on detection for each publish.

    @param      waitTopic       topic to subscribe to and wait for tracking data
    @param      publishTopic    topic to publish `detection` data on
    @param      timeout         seconds to wait before giving up
    @param      beginEpoch      initial time to use for timestamp
    @param      interval        how often to publish `detection`
    @param      detection       dict of detection information
    @return                     count of attempts before success, None on failure
    """

    # It's up to subclass to create self.pubsub
    log.debug("Waiting for ready", self.pubsub.isConnected(), waitTopic)
    self.pubsub.addCallback(waitTopic, self._trackingReceived)

    self._sceneReadyCondition = threading.Condition()
    max_count = timeout / interval
    count = 0
    ready = False

    # Make copy of detection since it will be modified
    detection_pub = detection.copy()
    self._sceneReadyCondition.acquire()
    while not ready and count < max_count:
      log.debug("Try", count, "of", max_count, publishTopic)
      detection_pub['timestamp'] = get_iso_time(beginEpoch + count * interval)
      self.pubsub.publish(publishTopic, json.dumps(detection_pub))
      if self._sceneReadyCondition.wait(interval):
        ready = True
      count += 1
    self._sceneReadyCondition.release()

    self.pubsub.removeCallback(waitTopic)

    del self._sceneReadyCondition

    return count if ready else None

  def objData(self):
    jdata = {"id": "camera1", "objects": {}, "rate": 9.8}
    obj = {"id": 1, "category": "person",
           "bounding_box": { "x": 0.56, "y": 0.0, "width": 0.24, "height": 0.49}}
    jdata['objects']['person'] = [obj]
    return jdata

  def getLocations(self):
    step = 0.02
    opposite = np.arange(-0.5, 0.6, step)
    across = np.flip(opposite)[2:]
    locations = np.concatenate((opposite, across))

    gap = np.array([abs(x - y) for x, y in zip(locations[:-1], locations[1:])])
    too_large = np.where(np.isclose(gap, step) == False)
    if len(too_large[0]):
      np.delete(locations, too_large[0])
    return locations

  def getScene(self):
    res = self.rest.getScenes({'id': self.params['scene_id']})
    assert res['results'], ("Scene does not exist", self.params['scene_id'], res.statusCode, res.errors)
    return

  def sceneScapeReady(self, max_attempts, controller_wait):
    attempts = 0
    ready = None
    frameRate = 10
    objData = self.objData()

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'])
    waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                   scene_id=self.params['scene_id'], thing_type="person")
    publishTopic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=objData['id'])
    self.pubsub.connect()
    self.pubsub.loopStart()

    while attempts < max_attempts:
      attempts += 1
      begin = get_epoch_time()
      ready = self.sceneControllerReady(waitTopic, publishTopic, controller_wait,
                                        begin, 1 / frameRate, objData)
      if ready:
        break
    else:
      log.error('Reached max number of attemps to wait for scene controller!')

    self.pubsub.loopStop()
    return True if ready else False
