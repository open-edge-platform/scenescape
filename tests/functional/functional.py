# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.diagnostic import Diagnostic
import numpy as np
import threading
import time
import json
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time, get_epoch_time
from tests.utils.log import get_logger

log = get_logger(__name__)

# Seconds to wait for the broker handshake before giving up on a connection.
MQTT_CONNECT_TIMEOUT_S = 10

# Detector bounding boxes are normalized to the image plane and must stay in
# [0, 1]. The projected foot is the bottom of the box (y + height). A short
# box lets that foot walk from north of the Demo ROI and tripwire to south of
# them without leaving the image plane. y in [0.00, 0.70] with height 0.05
# puts the foot in about [0.05, 0.75].
DEMO_SWEEP_BOX_HEIGHT = 0.05
DEMO_SWEEP_Y_STEP = 0.02
DEMO_SWEEP_Y_MAX = 0.70


def demo_sweep_locations(step=DEMO_SWEEP_Y_STEP, y_max=DEMO_SWEEP_Y_MAX):
  """Normalized box-y samples that cross the Demo scene and stay in [0, 1]."""
  opposite = np.arange(0.0, y_max + step / 2.0, step)
  across = np.flip(opposite)[2:]
  return np.concatenate((opposite, across))


def apply_demo_sweep_box(jdata, y, category="person"):
  """Stamp a schema-valid box whose foot follows the Demo crossing sweep."""
  box = jdata["objects"][category][0]["bounding_box"]
  box["height"] = DEMO_SWEEP_BOX_HEIGHT
  y = float(y)
  if not 0.0 <= y <= 1.0 or y + box["height"] > 1.0:
    raise ValueError(
      f"sweep box leaves normalized image plane: y={y} height={box['height']}")
  box["y"] = y
  return jdata

class FunctionalTest(Diagnostic):
  def buildArgparser(self):
    parser = self.argumentParser()
    parser.add_argument("--user", required=True, help="user to log into web server")
    parser.add_argument("--password", required=True, help="password to log into web server")
    parser.add_argument("--auth", default="/run/secrets/controller.auth",
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
      log.debug(f"Tracking received topic={message.topic} payload={data}")
      self._sceneReadyEvent.set()
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
    log.debug(
      f"Waiting for ready connected={self.pubsub.isConnected()} "
      f"topic={waitTopic}"
    )
    # Create the signal before subscribing
    self._sceneReadyEvent = threading.Event()
    self.pubsub.addCallback(waitTopic, self._trackingReceived)

    max_count = timeout / interval
    count = 0
    ready = False

    # Make copy of detection since it will be modified
    detection_pub = detection.copy()
    while not ready and count < max_count:
      log.debug(f"Try {count} of {max_count} publishTopic={publishTopic}")
      detection_pub['timestamp'] = get_iso_time(beginEpoch + count * interval)
      self.pubsub.publish(publishTopic, json.dumps(detection_pub))
      ready = self._sceneReadyEvent.wait(interval)
      count += 1

    self.pubsub.removeCallback(waitTopic)

    return count if ready else None

  def objData(self):
    jdata = {"id": "camera1", "objects": {}, "rate": 9.8}
    obj = {"id": 1, "category": "person",
           "bounding_box": { "x": 0.56, "y": 0.0, "width": 0.24, "height": 0.49}}
    jdata['objects']['person'] = [obj]
    return jdata

  def getLocations(self):
    return demo_sweep_locations()

  def getScene(self):
    scene_id = getattr(self, 'sceneUID', None) or self.params['scene_id']
    res = self.rest.getScenes({'id': scene_id})
    assert res['results'], ("Scene does not exist", scene_id, res.statusCode, res.errors)
    return

  def waitForConnection(self, pubsub, timeout=MQTT_CONNECT_TIMEOUT_S):
    """Block until `pubsub` reports a live broker connection.

    @param      pubsub      PubSub instance with its network loop started
    @param      timeout     seconds to wait before giving up
    @return                 True when connected, False on timeout
    """
    deadline = get_epoch_time() + timeout
    while not pubsub.isConnected() and get_epoch_time() < deadline:
      time.sleep(0.05)
    return pubsub.isConnected()

  def sceneScapeReady(self, max_attempts, controller_wait):
    attempts = 0
    ready = None
    frameRate = 10
    objData = self.objData()
    scene_id = getattr(self, 'sceneUID', None) or self.params['scene_id']

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'],
                         port=int(self.params['broker_port']))
    waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                   scene_id=scene_id, thing_type="person")
    publishTopic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=objData['id'])
    self.pubsub.connect()
    self.pubsub.loopStart()
    if not self.waitForConnection(self.pubsub):
      log.error('Timed out connecting to the broker; scene controller probe '
                'cannot subscribe or publish.')
      self.pubsub.loopStop()
      return False

    while attempts < max_attempts:
      attempts += 1
      begin = get_epoch_time()
      ready = self.sceneControllerReady(waitTopic, publishTopic, controller_wait,
                                        begin, 1 / frameRate, objData)
      if ready:
        break
    else:
      log.error('Reached max number of attempts to wait for scene controller!')

    self.pubsub.loopStop()
    return True if ready else False
