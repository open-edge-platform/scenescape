#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import socket
import threading

import paho.mqtt.client as mqtt

from scene_common import log
from scene_common.mqtt import PubSub

# The error constants in paho.mqtt.client are numbered wrong:
#   MQTT_ERR_AUTH is 11 yet the actual error number is 5
mqtt.MQTT_ERR_AUTH = 5

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("--broker", default="broker.scenescape.intel.com:1883",
                      help="hostname or IP of MQTT broker, optional :port")
  parser.add_argument("--brokerauth",
                      help="user:password or JSON file for MQTT authentication")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--cert", help="path to client certificate")
  return parser

class WaitForBroker:
  def __init__(self, broker, brokerauth, cert, rootcert):
    self.broker = broker
    self.brokerauth = brokerauth
    self.cert = cert
    self.rootcert = rootcert
    self.connectCondition = threading.Condition()
    return

  def connected(self, client, userdata, flags, rc):
    self.connectCondition.acquire()
    self.status = rc
    self.connectCondition.notify()
    self.connectCondition.release()
    return

  def fullExceptionName(self, ex):
    name = ex.__class__.__name__
    module = ex.__class__.__module__
    if module is not None and module != str.__class__.__module__:
      name = module + "." + name
    return name

  def wait(self):
    pubsub = PubSub(self.brokerauth, self.cert, self.rootcert, self.broker, keepalive=60)
    pubsub.onConnect = self.connected
    pubsub.loopStart()
    self.status = None

    self.connectCondition.acquire()
    tryConnect = True
    interval = 2

    while self.status not in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_AUTH):
      try:
        if tryConnect:
          pubsub.connect()
          tryConnect = False
          interval = None
          self.status = "Connecting"
      except socket.gaierror:
        self.status = f"\"{pubsub.broker}\" not found"
      except OSError as ex:
        if ex.errno == 99:
          self.status = "Connection refused"
        else:
          self.status = str(ex)
      except Exception as ex:
        self.status = f"{self.fullExceptionName(ex)} {ex}"
      log.info(f"Broker {self.broker} online: {self.status}")
      if self.connectCondition.wait(timeout=interval):
        break

    self.connectCondition.release()
    log.info(f"Broker {self.broker} online: {self.status}")
    if self.status == mqtt.MQTT_ERR_AUTH:
      exit(1)

    return

def main():
  args = build_argparser().parse_args()
  wfb = WaitForBroker(args.broker, args.brokerauth, args.cert, args.rootcert)
  wfb.wait()
  return

if __name__ == '__main__':
  exit(main() or 0)
