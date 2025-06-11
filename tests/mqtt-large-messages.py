#!/usr/bin/env -S python3 -u
import argparse
import os
import base64
import json
import numpy as np
import time
import tempfile
import subprocess
import yaml
from threading import Condition

try:
  # These only exist inside the container
  from scene_common.mqtt import PubSub
  from scene_common.timestamp import get_epoch_time
except ModuleNotFoundError:
  pass

TEST_NAME = "NEX-T10462"
TOPIC = "test/large-message"
MESSAGE_COUNT = 100
MOSQUITTO_CONF = """
listener 1883
listener 1884
protocol websockets
allow_anonymous true
max_packet_size 104857600
"""

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("yml", nargs="?", default="tests/compose/broker.yml",
                      help="yml of mosquitto broker")
  parser.add_argument("--broker", help="host:port of broker to use for testing")
  return parser

class LargeMessageTest:
  def __init__(self, broker, auth, cert, rootcert):
    image = np.random.rand(1080, 1920, 3) * 255
    image = image.astype('uint8')
    self.image_b64 = base64.b64encode(image).decode('utf-8')
    self.delay = 0

    self.wsReceived = Condition()

    self.client = PubSub(auth, cert, rootcert, broker, insecure=True)
    self.client.onDisconnect = self.mqttDisconnect
    self.client.connect()

    self.websocketReady = False
    ws = PubSub(auth, cert, rootcert, broker, 1884, insecure=True, transport="websockets")
    ws.onConnect = self.websocketConnect
    ws.onDisconnect = self.websocketDisconnect
    ws.onSubscribe = self.websocketSubscribe
    ws.onMessage = self.websocketReceived
    ws.connect()
    ws.loopStart()
    return

  def sendReceive(self):
    while not self.websocketReady:
      continue

    self.sendIDs = range(MESSAGE_COUNT)
    self.receiveIDs = []
    for idx in self.sendIDs:
      for retry in range(1):
        res = self.client.publish(TOPIC,
                                  json.dumps({'id': idx,
                                              'data': self.image_b64,
                                              'time': get_epoch_time()}),
                                  qos=2)
        print("Publish", idx, res)
        if res[0] != 0:
          break
        with self.wsReceived:
          if self.delay > 2:
            self.delay = 1
            if self.wsReceived.wait(self.delay):
              break
      print("Jitter value: ", self.delay)
      if self.delay > 2:
        self.delay = 1
        time.sleep(self.delay)
      if retry == 1 or res[0] != 0:
        break

    print("Jitter final value: ", self.delay)
    time.sleep(self.delay)

    assert len(self.receiveIDs) == len(self.sendIDs)
    return

  def websocketConnect(self, client, userdata, flags, rc):
    print("WS connect")
    client.subscribe(TOPIC)
    return

  def websocketSubscribe(self, client, userdata, mid, grabted_qos):
    self.websocketReady = True
    print("WS ready")
    return

  def websocketReceived(self, client, userdata, message):
    msg = str(message.payload.decode("utf-8"))
    jdata = json.loads(msg)
    idx = jdata['id']
    self.receiveIDs.append(idx)
    now = get_epoch_time()
    self.delay = now - jdata['time']
    with self.wsReceived:
      self.wsReceived.notify()
    print("WS received", idx, self.delay, len(msg))
    return

  def websocketDisconnect(self, client, userdata, rc):
    print("Websocket disconnected")
    return

  def mqttDisconnect(self, client, userdata, rc):
    print("Broker disconnected")
    return

def main():
  print("Executing:", TEST_NAME)
  error = 1

  args = build_argparser().parse_args()

  if args.broker:
    lmtest = LargeMessageTest(args.broker, None, None, None)
    lmtest.sendReceive()
    error = 0

  else:
    # Start broker and message test inside containers
    tmp_conf = tempfile.NamedTemporaryFile()
    tmp_conf.write(MOSQUITTO_CONF.encode())
    tmp_conf.flush()

    project_name = "large-message-test"
    network_name = "scenescape-test"

    override = {
      'services': {
        'broker': {
          'networks': [
            network_name
          ],
          'volumes': [
            tmp_conf.name + ":" + "/etc/mosquitto/mosquitto.conf",
          ],
          'restart': "no"
        }
      }
    }
    override_yaml = yaml.dump(override)
    print("OVERRIDE", override_yaml)
    tmp_override = tempfile.NamedTemporaryFile(suffix=".yml")
    tmp_override.write(override_yaml.encode())
    tmp_override.flush()

    cmd = ["docker", "compose", "--project-directory", os.getcwd(),
           "--project-name", project_name,
           "-f", args.yml, "-f", tmp_override.name,
           "up"]
    print(" ".join(cmd))
    broker_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in broker_process.stdout:
      line = line.decode()
      print(line.rstrip())
      if 'mosquitto' in line and 'running' in line:
        break

    try:
      cmd = ["docker/scenescape-start",
             "--network", project_name + "_" + network_name,
             os.path.relpath(__file__),
             "--broker", "broker.scenescape.intel.com"]
      print(" ".join(cmd))
      test_error = subprocess.run(cmd).returncode
      print("ERROR", test_error)
    finally:
      # Make sure broker is still running
      broker_error = broker_process.poll() is not None
      print("Broker still running:", not broker_error)

      time.sleep(1)
      cmd = ["docker", "compose", "--project-directory", os.getcwd(),
             "--project-name", project_name,
             "-f", args.yml, "-f", tmp_override.name,
             "down"]
      print(" ".join(cmd))
      subprocess.run(cmd)

      error = test_error or broker_error
      print(f"{TEST_NAME}:", "PASS" if not error else "FAIL")

  return error

if __name__ == '__main__':
  exit(main() or 0)
