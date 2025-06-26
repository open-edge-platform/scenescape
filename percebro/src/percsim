#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import sys, os
from argparse import ArgumentParser
import json
import time

from scene_common.json_track_data import CamManager
from scene_common.timestamp import get_iso_time, get_epoch_time
from scene_common.mqtt import PubSub

TestName="JSON Detection Publishing"
TEST_WAIT_TIME=20
connected = False

def buildArgparser():
  parser = ArgumentParser()
  parser.add_argument("input", nargs="+",
                      help="Detection JSON file text files.")
  parser.add_argument("--rate", default=30.0, type=float,
                      help="Framerate desired to push the detections at.")
  parser.add_argument("--frames", type=int,
                      help="Number of 'frames' desired to push.")
  parser.add_argument("-b", "--broker", default="broker.scenescape.intel.com",
                      help="hostname or IP of MQTT broker")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--cert", help="path to client certificate")
  parser.add_argument("--auth", help="user:password or JSON file for MQTT authentication")
  parser.add_argument("--loop", help="Loop input files", action="store_true")
  return parser

def processObjects(objects):
  sorted_objs = {}
  for obj in objects:
    otype = obj['category']
    if otype not in sorted_objs:
      sorted_objs[otype] = []
    sorted_objs[otype].append(obj)
  return sorted_objs

def load_input_files(inputs, frames):
  detection_data = []
  detection_files = 0
  for input in inputs:
    print("Loading input file {}".format(input))
    try:
      with open( input, 'r' ) as det_file:
        cur_file = {}
        cur_file['data'] = det_file.readlines()
        if frames is not None:
          cur_file['frames'] = frames
        else:
          cur_file['frames'] = len(cur_file['data'])
        cur_file['current'] = 0
        cur_file['sent'] = 0
        detection_data.append(cur_file)
        detection_files += 1
    except:
      print("Failed opening Input {}".format(input))

  return detection_files, detection_data

def on_connect(mqttc, obj, flags, rc):
  """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    flags     The response sent by the broker.
  @param    rc        The connection result.
  @return   None.
  """
  global connected
  connected = True
  print("Connected")
  return None

def collect_mqtt_msgs(client):
  """! Collects MQTT messages using callback method on_message().
  @param    client                  MQTT client.
  @return   None.
  """
  client.loopStart()
  time.sleep(TEST_WAIT_TIME)
  client.loopStop()
  return None

def connectToMQTT(auth, cert, rootcert, broker):
  client = PubSub(auth, cert, rootcert, broker)
  client.onConnect = on_connect
  print("Connecting to broker", broker)
  client.connect()
  return client

def main():
  global TestName, connected
  args = buildArgparser().parse_args()

  print("Loading input files")
  mgr = CamManager(args.input, scene=None)

  client = connectToMQTT(args.auth, args.cert, args.rootcert, args.broker)

  total_messages_published = 0
  total_loops_published = 0
  total_detections_published = 0
  total_time = 0

  test_start_time = get_epoch_time()
  loop_done = False
  delay_per_frame = 1.0 / args.rate
  print("Delay per frame {:.3f}".format(delay_per_frame))
  current_frame_out = 0
  collect_mqtt_msgs(client)
  assert connected
  while loop_done == False:
    time_start = get_epoch_time()

    now = test_start_time + delay_per_frame * current_frame_out
    current_objects_published = 0

    jcount, camDetect, frame = mgr.nextFrame(scene=None, loop=args.loop)

    if len(camDetect['objects']):
      sorted_objs = processObjects(camDetect['objects'])

      camDetect['timestamp'] = get_iso_time(now)
      camDetect['frame'] = current_frame_out

      for category in sorted_objs:
        camDetect['objects'] = sorted_objs[category]
        camDetect['real_stamp'] = get_epoch_time()
        line = json.dumps(camDetect).strip()
        topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camDetect['id'])
        mqttinfo = client.publish(topic, line)
        if not mqttinfo.is_published():
          print("Failed sending!", mqttinfo.rc)

      total_messages_published += 1

    total_detections_published += len(camDetect['objects'])
    current_objects_published += len(camDetect['objects'])
    current_frame_out += 1

    if args.frames and current_frame_out >= args.frames:
      break

    time_end = get_epoch_time()
    time_next = time_start + delay_per_frame
    err_now = time_end - now
    sleep_needed = (time_next - time_end) - err_now
    if sleep_needed > 0:
      time.sleep(sleep_needed)

    time_end = get_epoch_time()
    if total_messages_published > 0 and total_messages_published % 100 == 0:
      current_time = time_end - test_start_time
      message_rate = total_messages_published / current_time
      usable_message_rate = total_loops_published / current_time
      print("Det {}, obj {}, Current rate {} / {}"
             .format(total_messages_published, total_detections_published,
                      message_rate, usable_message_rate))
      sys.stdout.flush()
  test_end_time = get_epoch_time()
  total_time = test_end_time - test_start_time

  message_rate = total_messages_published / total_time
  object_rate = total_detections_published / total_time
  print("GEN: {}: Ran {:.3f} s, {} messages, {} detections published"
         .format(TestName, total_time, total_messages_published, total_detections_published))
  print("GEN: Message Rate {:.3f}, Detection Rate {:.3f}".format(message_rate,
      object_rate))
  if message_rate * 1.10 < args.rate:
    print("GEN: WARNING: Test could not keep up with desired rate.")
  time.sleep(20)

  return 0

if __name__ == '__main__':
  os._exit(main() or 0)
