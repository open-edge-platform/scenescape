# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading

from scene_common import log
from scene_common.mqtt import PubSub

class AnalyticsContext:
  topics_to_subscribe = []

  def __init__(self, broker, broker_auth, cert, root_cert, rest_url, rest_auth):
    
    data_regulated_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id="+")
    self.topics_to_subscribe.append((data_regulated_topic, self.updateScenes))  

    self.register_thread_lock = threading.Lock()
    self.current_processing_scene = None
    self.client = PubSub(broker_auth, cert, root_cert, broker, keepalive=240)
    self.client.onConnect = self.mqttOnConnect
    self.client.connect()

    return

  def mqttOnConnect(self, client, userdata, flags, rc):
    """! Subscribes to a list of topics on MQTT.
    @param   client    Client instance for this callback.
    @param   userdata  Private user data as set in Client.
    @param   flags     Response flags sent by the broker.
    @param   rc        Connection result.

    @return  None
    """
    for topic, callback in self.topics_to_subscribe:
      log.info("Subscribing to " + topic)
      self.client.addCallback(topic, callback)
      log.info("Subscribed " + topic)
    return

  def updateScenes(self, client, userdata, message):
    """! MQTT callback function used to update the scene data that has been stored in the
    database whenever there is an update in the scene model.
    @param   client      MQTT client.
    @param   userdata    Private user data as set in Client.
    @param   message     Message on MQTT bus.

    @return  None
    """
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      topic = PubSub.parseTopic(message.topic)
      sceneobj = self.calibration_data_interface.sceneWithID(topic['scene_id'])
      if sceneobj and sceneobj.camera_calibration != "Manual":
        if self.scene_strategies[sceneobj.camera_calibration].isMapUpdated(sceneobj):
          self.scene_strategies[sceneobj.camera_calibration].resetScene(sceneobj)
          self.sceneUpdateThreadWrapper(sceneobj, map_update=True)
    return

  def loopForever(self):
    return self.client.loopForever()
