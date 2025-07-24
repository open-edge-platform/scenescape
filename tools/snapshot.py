#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import base64
import json

import cv2
import numpy as np

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time


def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                   description='Sample of generating a snapshot and publishing it over MQTT upon request.')

  parser.add_argument('-b', '--broker',
                      help='MQTT broker',
                      default='localhost')

  parser.add_argument('--port',
                      type=int,
                      help='MQTT port',
                      default=1883)

  parser.add_argument('-a', '--auth',
                      help='Scenescape Auth file')

  parser.add_argument('-p', '--password',
                      help='MQTT password')

  parser.add_argument('-u', '--username',
                      help='MQTT user name')

  parser.add_argument('-i', '--id',
                      help='Sensor ID (or mqttid)',
                      required=True)

  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")

  return parser.parse_args()

# Define MQTT callbacks
def on_message(client, userdata, message):
  if str(message.payload.decode("utf-8")) == "getimage":
    # Get the current timestamp
    timestamp = get_iso_time()

    # Use actual snapshot frame here, but for now use a blank frame
    # with a timestamp printed on it
    frame = np.zeros((1080, 1920, 3), np.uint8)
    font = cv2.FONT_HERSHEY_DUPLEX
    text = str(timestamp)
    textsize = cv2.getTextSize(text, font, 1, 2)[0]
    posX = (frame.shape[1] - textsize[0]) // 2
    posY = (frame.shape[0] + textsize[1]) // 2
    cv2.putText(frame, text, (posX, posY), font, 1, (255, 255, 255), 2)

    # Create base64 encoded JPEG image from the frame
    ret, jpeg = cv2.imencode(".jpg", frame)
    jpeg = base64.b64encode(jpeg).decode('utf-8')

    # Generate the message with a timestamp and the encoded frame
    message_dict = {'timestamp': timestamp, 'image': jpeg, 'id': userdata.id}

    # Publish the message to the image topic
    topic = PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id=userdata.id)
    client.publish(topic, json.dumps(message_dict))

  else:
    print("Received message: ", str(message.payload.decode("utf-8")))

  return

def on_log(client, userdata, level, buf):
  print("Log: ", buf)

  return

def on_connect(client, userdata, flags, rc):
  print("Connected.")

  return

def main():
  args = build_argparser()
  auth_str = args.auth
  if auth_str is None:
    auth_str = args.username + ':' + args.password

  client = PubSub(auth_str, None, args.rootcert, args.broker, args.port, 60, userdata=args)
  client.onMessage = on_message
  client.onLog = on_log
  client.onConnect = on_connect

  print("Connecting to broker...")

  # Connect and subscribe to the command topic
  client.connect()
  client.subscribe(PubSub.formatTopic( PubSub.CMD_CAMERA, camera_id=args.id))
  client.loopForever()

  return

if __name__ == '__main__':
  exit(main() or 0)
