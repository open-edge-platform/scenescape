# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common import log
from scene_common.mqtt import PubSub


class ChildSceneController():
  def __init__(self, root_cert, info, parent_controller):

    self.child_name = info['name']
    self.child_id = info['remote_child_id']
    self.parent_controller = parent_controller
    self.connected = False

    self.client = PubSub(cert=None, rootca=root_cert, broker=info.get('host_name', None),
                         auth=f"{info.get('mqtt_username', None)}:{info.get('mqtt_password', None)}",
                         keepalive=240)
    self.client.onConnect = self.onChildConnect
    self.client.onDisconnect = self.onChildDisconnect
    self.child_scene_topic = PubSub.formatTopic(PubSub.DATA_EXTERNAL,
                                                scene_id=self.child_id, thing_type="+")
    self.child_event_topic = PubSub.formatTopic(PubSub.EVENT,
                                                region_type="+", event_type="+",
                                                scene_id=self.child_id, region_id="+")
    try:
      self.client.connect()
    except Exception as e:
      # FIXME - remove this error published , handle known exceptions.
      self.handleException(str(e))
    return

  def handleException(self, e):
    log.debug("Exception: ", e)
    self.parent_controller.pubsub.publish(PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS,
                                                             scene_name=self.child_id), e)
    return

  def onChildConnect(self, client, userdata, flags, rc):
    if rc == 5:
      self.handleException("Invalid credentials")
      return
    log.info(f"Connected to remote child {self.child_name} with result code {rc}")

    self.connected = True
    self.parent_controller.pubsub.publish(PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS,
                                          scene_name=self.child_id), "connected")

    self.client.addCallback(self.child_event_topic, self.parent_controller.republishEvents)
    log.info("Subscribed to", self.child_event_topic)

    self.client.addCallback(self.child_scene_topic,
                            self.parent_controller.handleMovingObjectMessage)
    log.info("Subscribed to", self.child_scene_topic)

    return

  def publishStatus(self, client, userdata, message):
    message = message.payload.decode('utf-8')
    if message == "isConnected":
      self.parent_controller.pubsub.publish(PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS,
                          scene_name=self.child_id), "connected" if self.connected else "disconnected")
    return

  def onChildDisconnect(self, client, userdata, rc):
    self.connected = False
    log.info(f"Disconnected remote child {self.child_name}")

    self.parent_controller.pubsub.publish(PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS,
                        scene_name=self.child_id), "disconnected")
    return

  def loopStart(self):
    return self.client.loopStart()

  def loopStop(self):
    return self.client.loopStop()
