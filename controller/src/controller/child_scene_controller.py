# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import orjson

from scene_common import log
from scene_common.mqtt import PubSub


class ChildSceneController():
  def __init__(self, root_cert, info, parent_controller):

    self.child_name = info['name']
    self.child_id = info['remote_child_id']
    self.child_link_uid = info.get('uid')
    self.parent_controller = parent_controller
    self.connected = False
    self.remote_config = dict(info)  # keep the full existing remote child row
    self._last_tripwires_json = None

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
                                                             scene_id=self.child_id), e)
    return

  def onChildConnect(self, client, userdata, flags, rc):
    if rc == 5:
      self.handleException("Invalid credentials")
      return
    log.info(f"Connected to remote child {self.child_name} with result code {rc}")

    self.connected = True
    self.parent_controller.pubsub.publish(PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS,
                                                             scene_id=self.child_id), "connected")

    # Remove stale callbacks from any previous connection before re-adding
    self.client.removeCallback(self.child_event_topic)
    self.client.removeCallback(self.child_scene_topic)
    tripwires_response_topic = PubSub.formatTopic(PubSub.CMD_CHILD_TRIPWIRES_RESPONSE,
                                                  scene_id=self.child_id)
    self.client.removeCallback(tripwires_response_topic)

    self.client.addCallback(self.child_event_topic, self.parent_controller.republishEvents)
    log.info("Subscribed to", self.child_event_topic)

    self.client.addCallback(self.child_scene_topic,
                            self.parent_controller.handleMovingObjectMessage)
    log.info("Subscribed to", self.child_scene_topic)

    self.client.addCallback(tripwires_response_topic, self.handleTripwiresResponse)
    log.info("Subscribed to", tripwires_response_topic)

    tripwires_request_topic = PubSub.formatTopic(PubSub.CMD_CHILD_TRIPWIRES_REQUEST,
                                                 scene_id=self.child_id)
    self.client.publish(tripwires_request_topic, "request")
    log.info("Requested tripwires from child", self.child_name)
    return

  def handleTripwiresResponse(self, client, userdata, message):
    log.debug(
      f"Tripwire callback: child={self.child_name} "
      f"link_uid={self.child_link_uid} topic={message.topic} "
      f"payload={message.payload}"
    )

    if not self.child_link_uid:
      log.warning(f"Cannot persist tripwires for child {self.child_name}: no child_link_uid")
      return

    try:
      tripwires = orjson.loads(message.payload.decode('utf-8'))
    except (orjson.JSONDecodeError, UnicodeDecodeError) as e:
      log.error(f"Invalid tripwires payload from child {self.child_name}: {e}")
      return

    if not isinstance(tripwires, list):
      log.error(f"Unexpected tripwires payload type from child {self.child_name}")
      return

    # Persist the tripwires to the database only if they have changed
    normalized = orjson.dumps(tripwires, option=orjson.OPT_SORT_KEYS)
    if normalized == self._last_tripwires_json:
      log.debug(f"Tripwires unchanged for child {self.child_name}; skipping persist")
      return
    self._last_tripwires_json = normalized

    try:
      result = self.parent_controller.cache_manager.data_source.updateChildScene(
        self.child_link_uid,
        {'cached_tripwires': tripwires}
      )
      if result.status_code != 200 or result.errors:
        log.error(
          f"Failed to persist tripwires for child {self.child_name}: "
          f"status={result.status_code} errors={result.errors}"
        )
    except Exception as e:
      log.error(f"Failed to persist tripwires for child {self.child_name}: {e}")

  def publishStatus(self, client, userdata, message):
    msg = message.payload.decode('utf-8')
    if msg == "isConnected":
      self.parent_controller.pubsub.publish(
        PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_id=self.child_id),
        "connected" if self.connected else "disconnected"
      )
    return

  def onChildDisconnect(self, client, userdata, rc):
    self.connected = False
    log.info(f"Disconnected remote child {self.child_name}")

    self.parent_controller.pubsub.publish(PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS,
                        scene_id=self.child_id), "disconnected")
    return

  def loopStart(self):
    return self.client.loopStart()

  def loopStop(self):
    return self.client.loopStop()
