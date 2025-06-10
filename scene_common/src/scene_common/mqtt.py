# Copyright (C) 2021-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import json
import os
import paho.mqtt.client as mqtt
import re
import struct
import threading
from enum import Enum, auto
from string import Template

from scene_common import log

# FIXME - find a way for javascript/HTML to use these and not hardcode topics

TOPIC_BASE = "scenescape"
CHUNK_HEADER = "> LLHH"
CHUNK_SIZE = 1024 * 1024

class _Topic(Enum):
  CHANNEL = auto()
  CMD_AUTOCALIB_SCENE = auto()
  CMD_CAMERA = auto()
  CMD_DATABASE = auto()
  CMD_KUBECLIENT = auto()
  CMD_SCENE_UPDATE = auto()
  DATA_AUTOCALIB_CAM_POSE = auto()
  DATA_CAMERA = auto()
  DATA_EXTERNAL = auto()
  DATA_REGION = auto()
  DATA_REGULATED = auto()
  DATA_SCENE = auto()
  DATA_SENSOR = auto()
  EVENT = auto()
  IMAGE_CALIBRATE = auto()
  IMAGE_CAMERA = auto()
  SYS_AUTOCALIB_STATUS = auto()
  SYS_CHILDSCENE_STATUS = auto()
  SYS_PERCEBRO_STATUS = auto()

# Really gross way to put above constants directly into PubSub class
class _PubSubTopicBase:
  pass

for key in _Topic:
  setattr(_PubSubTopicBase, key.name, key)

class PubSub(_PubSubTopicBase):
  _TopicTemplates = {
    _Topic.CHANNEL: Template(TOPIC_BASE + "/channel/${channel}"),
    _Topic.CMD_AUTOCALIB_SCENE: Template(TOPIC_BASE + "/cmd/autocalibration/scene/${scene_id}"),
    _Topic.CMD_CAMERA: Template(TOPIC_BASE + "/cmd/camera/${camera_id}"),
    _Topic.CMD_DATABASE: Template(TOPIC_BASE + "/cmd/database"),
    _Topic.CMD_KUBECLIENT: Template(TOPIC_BASE + "/cmd/kubeclient"),
    _Topic.CMD_SCENE_UPDATE: Template(TOPIC_BASE + "/cmd/scene/update/${scene_id}"),
    _Topic.DATA_AUTOCALIB_CAM_POSE: Template(TOPIC_BASE + "/autocalibration/camera/pose/${camera_id}"),
    _Topic.DATA_CAMERA: Template(TOPIC_BASE + "/data/camera/${camera_id}"),
    _Topic.DATA_EXTERNAL: Template(TOPIC_BASE + "/external/${scene_id}/${thing_type}"),
    _Topic.DATA_REGION: Template(TOPIC_BASE + "/data/region/${scene_id}/${region_id}/${thing_type}"),
    _Topic.DATA_REGULATED: Template(TOPIC_BASE + "/regulated/scene/${scene_id}"),
    _Topic.DATA_SCENE: Template(TOPIC_BASE + "/data/scene/${scene_id}/${thing_type}"),
    _Topic.DATA_SENSOR: Template(TOPIC_BASE + "/data/sensor/${sensor_id}"),
    _Topic.EVENT: Template(TOPIC_BASE + "/event/${region_type}/${scene_id}/${region_id}/${event_type}"),
    _Topic.IMAGE_CALIBRATE: Template(TOPIC_BASE + "/image/calibration/camera/${camera_id}"),
    _Topic.IMAGE_CAMERA: Template(TOPIC_BASE + "/image/camera/${camera_id}"),
    _Topic.SYS_AUTOCALIB_STATUS: Template(TOPIC_BASE + "/sys/autocalibration/status"),
    _Topic.SYS_CHILDSCENE_STATUS: Template(TOPIC_BASE + "/sys/child/status/${scene_name}"),
    _Topic.SYS_PERCEBRO_STATUS: Template(TOPIC_BASE + "/sys/percebro/status/${camera_id}"),
  }

  def __init__(self, auth, cert, rootca, broker, port=None, keepalive=60,
               insecure=False, transport="tcp", userdata=None):
    self.broker = broker
    self.port = port
    self.keepalive = keepalive

    if self.broker is not None and ':' in self.broker:
      if self.port is not None:
        raise ValueError("Port specified both in broker and port argument",
                         self.broker, self.port)
      self.broker, self.port = self.broker.split(':')
      self.port = int(self.port)

    if self.port is None:
      self.port = 1883

    certs = None
    if rootca is not None and os.path.exists(rootca):
      if certs is None:
        certs = {}
      if 'ca_certs' not in certs:
        certs['ca_certs'] = rootca
    if cert is not None:
      if certs is None:
        certs = {}

    self.client = initializeMqttClient(transport=transport, userdata=userdata)
    if not self.checkTlsConnection(certs, transport, userdata):
      return

    if auth is not None:
      user = pw = None
      if os.path.exists(auth):
        with open(auth) as json_file:
          data = json.load(json_file)
        user = data['user']
        pw = data['password']
      else:
        sep = auth.find(':')
        if sep < 0:
          raise ValueError("Invalid user/password")
        user = auth[:sep]
        pw = auth[sep+1:]
      self.client.username_pw_set(user, pw)

    return

  @classmethod
  def getTopicByTemplateName(cls, topic_name):
    try:
      topic_enum = _Topic[topic_name]
      return cls._TopicTemplates[topic_enum]
    except KeyError:
      print(f"Topic '{topic_name}' not found.")
      return None

  @classmethod
  def match_topic(cls, template, topic):
    if template == topic:
      return topic

    regex = re.escape(template)
    regex = regex.replace(r'\$\{thing_type\}', r'([^/]+)')
    regex = regex.replace(r'\$\{camera_id\}', r'([^/]+)')
    regex = regex.replace(r'\$\{scene_id\}', r'([^/]+)')
    regex = regex.replace(r'\$\{channel\}', r'([^/]+)')
    regex = regex.replace(r'\$\{scene_name\}', r'([^/]+)')
    regex = regex.replace(r'\$\{region_id\}', r'([^/]+)')
    regex = regex.replace(r'\$\{sensor_id\}', r'([^/]+)')
    regex = regex.replace(r'\$\{region_type\}', r'([^/]+)')
    regex = regex.replace(r'\$\{event_type\}', r'([^/]+)')
    pattern = re.compile(f'^{regex}$', re.IGNORECASE)

    match = pattern.fullmatch(topic)
    if match:
      return match.groups()
    return None

  def onTlsConnect(self, client, userdata, flags, rc):
    if rc == mqtt.CONNACK_ACCEPTED:
      log.info("connection accepted")
    else:
      log.info("connection failed")
    return

  def checkTlsConnection(self, certs, transport, userdata):
    self.client.on_connect = self.onTlsConnect
    try:
      self.client.tls_set(**certs)
      self.client.connect(self.broker, self.port, 60)
      return True

    except Exception as e:
      self.client = initializeMqttClient(transport=transport, userdata=userdata)
      return False

  def connect(self):
    return self.client.connect(self.broker, self.port, self.keepalive)

  def subscribe(self, topic, qos=0):
    return self.client.subscribe(topic, qos)

  def unsubscribe(self, topic):
    return self.client.unsubscribe(topic)

  def addCallback(self, topic, callback, qos=0):
    self.client.message_callback_add(topic, self.wrapCallback(callback))
    return self.subscribe(topic, qos)

  def removeCallback(self, topic):
    self.client.message_callback_remove(topic)
    return self.unsubscribe(topic)

  def publish(self, topic, payload, qos=0, retain=False):
    return self.client.publish(topic, payload, qos, retain)

  def disconnect(self):
    return self.client.disconnect()

  def loopForever(self):
    return self.client.loop_forever()

  def loopStart(self):
    return self.client.loop_start()

  def loopStop(self):
    return self.client.loop_stop()

  def isConnected(self):
    return self.client.is_connected()

  @property
  def onConnect(self):
    return self.client.on_connect

  @onConnect.setter
  def onConnect(self, value):
    self.client.on_connect = self.wrapCallback(value)
    return

  @property
  def onDisconnect(self):
    return self.client.on_disconnect

  @onDisconnect.setter
  def onDisconnect(self, value):
    self.client.on_disconnect = self.wrapCallback(value)
    return

  @property
  def onMessage(self):
    return self.client.on_message

  @onMessage.setter
  def onMessage(self, value):
    self.client.on_message = self.wrapCallback(value)
    return

  @property
  def onPublish(self):
    return self.client.on_publish

  @onPublish.setter
  def onPublish(self, value):
    self.client.on_publish = self.wrapCallback(value)
    return

  @property
  def onSubscribe(self):
    return self.client.on_subscribe

  @onSubscribe.setter
  def onSubscribe(self, value):
    self.client.on_subscribe = self.wrapCallback(value)
    return

  @property
  def onUnsubscribe(self):
    return self.client.on_unsubscribe

  @onUnsubscribe.setter
  def onUnsubscribe(self, value):
    self.client.on_unsubscribe = self.wrapCallback(value)
    return

  @property
  def onLog(self):
    return self.client.on_log

  @onLog.setter
  def onLog(self, value):
    self.client.on_log = self.wrapCallback(value)
    return

  def wrapCallback(self, function):
    """Wraps callback functions that are a passed into the internal client object so that
       callbacks can make use of the PubSub object instead of the default client.
    """
    def wrapper(*args, **kwargs):
      modified_args = list(args)
      modified_args[0] = self
      return function(*modified_args, **kwargs)
    return wrapper

  @staticmethod
  def formatTopic(topic_id, **kwargs):
    """Creates a topic string using named identifiers passed as
       arguments.
    """

    for key, val in kwargs.items():
      if isinstance(val, str) and '/' in val:
        raise ValueError("Slashes not allowed in", key)
    return PubSub._TopicTemplates[topic_id].substitute(kwargs)

  @staticmethod
  def parseTopic(topic_string):
    """Parses received topic and splits it out into a dictionary with
       named identifiers and the values they were set to.
    """

    topic_split = topic_string.split('/')
    best_match = best_variables = None
    best_score = 0
    for key, templ in PubSub._TopicTemplates.items():
      vsplit = templ.template.split('/')
      if len(vsplit) != len(topic_split):
        continue

      static_score = var_score = 0
      var_positions = []
      for idx, (v_element, t_element) in enumerate(zip(vsplit, topic_split)):
        if v_element == t_element:
          static_score += 1
        elif v_element.startswith("$"):
          var_positions.append(idx)
          var_score += 1
      if static_score + var_score == len(vsplit) \
         and static_score > best_score:
        best_match = key
        best_variables = var_positions

    if best_match is not None:
      parsed = {"_topic_id": best_match}
      vsplit = PubSub._TopicTemplates[best_match].template.split('/')
      for idx in best_variables:
        parsed[vsplit[idx][2:-1]] = topic_split[idx]
      return parsed

    return None

  # Raise errors if someone tries to access wrong attribute
  @property
  def on_connect(self):
    raise NotImplementedError

  @property
  def on_disconnect(self):
    raise NotImplementedError

  @property
  def on_message(self):
    raise NotImplementedError

  @property
  def on_publish(self):
    raise NotImplementedError

  @property
  def on_subscribe(self):
    raise NotImplementedError

  @property
  def on_unsubscribe(self):
    raise NotImplementedError

  @property
  def on_log(self):
    raise NotImplementedError

  def sendFile(self, topic, file):
    if isinstance(file, str):
      with open(file, mode="rb") as f:
        self.sendFile(topic, f)
      return

    file.seek(0, os.SEEK_END)
    totalSize = file.tell()
    chunkCount = (totalSize + CHUNK_SIZE - 1) // CHUNK_SIZE

    file.seek(0)
    for idx in range(chunkCount):
      header = struct.pack(CHUNK_HEADER, totalSize, CHUNK_SIZE, chunkCount, idx)
      data = file.read(CHUNK_SIZE)
      print("Publishing chunk:", idx, chunkCount, len(data), topic)
      self.publish(topic, header + data, qos=2)

    return

  def receiveFile(self, topic, timeout=1):
    self.received = None
    self.complete = False
    self.receivedCondition = threading.Condition()
    self.addCallback(topic, self.chunkReceived)
    self.receivedCondition.acquire()
    while True:
      found = self.receivedCondition.wait(timeout=timeout)
      if not found or self.complete:
        break
    self.receivedCondition.release()
    self.removeCallback(topic)

    if not self.complete:
      self.received = None
    return self.received

  def chunkReceived(self, client, userdata, message):
    # self and client are the same
    self.receivedCondition.acquire()

    headerLen = struct.calcsize(CHUNK_HEADER)
    header = struct.unpack(CHUNK_HEADER, message.payload[:headerLen])
    data = message.payload[headerLen:]

    totalSize = header[0]
    chunkSize = header[1]
    chunkCount = header[2]
    idx = header[3]

    if not hasattr(self, 'remaining') or self.remaining is None:
      self.remaining = list(range(chunkCount))
      self.received = bytearray(totalSize)

    if idx in self.remaining:
      offset = idx * chunkSize
      self.received[offset:offset + len(data)] = data
      self.remaining.remove(idx)
      self.complete = len(self.remaining) == 0

    self.receivedCondition.notify()
    self.receivedCondition.release()
    return

def initializeMqttClient(**kwargs):
  if hasattr(mqtt, 'CallbackAPIVersion'):
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, **kwargs)
  else:
    return mqtt.Client(**kwargs)
