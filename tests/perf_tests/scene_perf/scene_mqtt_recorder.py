#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import time
import os

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_epoch_time
from tests.mqtt_helper import TEST_MQTT_DEFAULT_ROOTCA, TEST_MQTT_DEFAULT_AUTH
from argparse import ArgumentParser

objects_detected = 0
log_file = None
number_sensors = 0
sensors_seen = []
proc_time_avg = 0
proc_time_count = 0

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("--interval", type=int, default=5,
                      help="Number of seconds to wait for message each interval")
  parser.add_argument("--output",
                      help="Location to save captured mqtt messages")
  return parser

def test_on_connect(mqttc, obj, flags, rc):
  print( "Connected" )
  mqttc.subscribe( PubSub.formatTopic(PubSub.DATA_SCENE, scene_id="+",
                                      thing_type="+"), 0 )
  return


def test_on_message(mqttc, obj, msg):
  global proc_time_avg, proc_time_count
  global objects_detected
  global log_file
  global number_sensors, sensors_seen
  time_rx = get_epoch_time()
  real_msg = str(msg.payload.decode("utf-8"))
  jdata = json.loads( real_msg )
  time_tx_det = jdata['real_stamp']

  time_rx_tstamp = get_epoch_time(jdata['timestamp'])
  time_proc_est = jdata['debug_hmo_processing_time']

  # This assumes the delay observed between TX at the detection generation
  # and the delay between scene controller and this module
  # are roughly the same (at least in average).

  proc_time_avg = ((proc_time_avg*proc_time_count) + time_proc_est)/(proc_time_count+1)
  proc_time_count += 1

  if log_file is not None:
    json.dump( jdata, log_file )
    log_file.write("\n")
  objects_detected += 1

  if jdata['id'] not in sensors_seen:
    number_sensors += 1
    sensors_seen.append(jdata['id'])
  return

def wait_to_start(test_wait, client):
  global objects_detected
  test_started = False
  waited_for = 0
  TEST_WAIT_START_TIME = 60
  TEST_WAIT_SIGNAL_TIME = 30
  TEST_WAIT_ABORT_TIME = 180

  time.sleep(TEST_WAIT_START_TIME)

  while test_started == False:
    time.sleep(test_wait)
    waited_for += test_wait
    print("Waiting for test to start.. {}".format(waited_for))
    if objects_detected != 0:
      test_started = True
    else:
      if waited_for > TEST_WAIT_ABORT_TIME:
        print("Failed waiting for test to start.")
        return False
  return True

def test_mqtt_recorder():
  global objects_detected
  global log_file
  global number_sensors
  global proc_time_avg, proc_time_count

  args = build_argparser().parse_args()

  result = 1
  supass = os.getenv('SUPASS')
  auth_string = f'admin:{supass}'
  client = PubSub(auth_string, None, TEST_MQTT_DEFAULT_ROOTCA,
                  "broker.scenescape.intel.com")

  client.onMessage = test_on_message
  client.onConnect = test_on_connect
  client.connect()

  test_loop_done = False
  test_empty_loops = 0
  test_max_empty_loops = 5
  test_wait = args.interval

  if args.output is not None:
    log_file = open( args.output, 'w' )

  client.loopStart()
  # Wait for test to start..

  if wait_to_start(test_wait, client) == False:
    client.loopStop()

    if args.output is not None:
      log_file.close()
    return 1

  test_start_time = get_epoch_time()
  cur_det_objects = objects_detected
  old_det_objects = cur_det_objects
  while test_loop_done == False:
    time.sleep(test_wait)
    new_det_objects = objects_detected

    cycle_det_objects = new_det_objects - old_det_objects
    print( "New {} total {}".format( cycle_det_objects, new_det_objects) )
    cur_rate = cycle_det_objects / test_wait

    if cycle_det_objects == 0:
      test_empty_loops += 1

      # If there is only one publisher, it is more likely we wont see objects for some period of time,
      # so trying not to end too quickly.
      if number_sensors == 1:
        if test_empty_loops == test_max_empty_loops*2:
          test_loop_done = True
          print( "No messages detected! (1 sensor)" );
      elif test_empty_loops == test_max_empty_loops:
        test_loop_done = True
        print( "No messages detected! ({} sensors)".format(number_sensors) );
    else:
      test_empty_loops = 0

    print( "Current rate incoming {:.3f} messages/ss".format(cur_rate) )
    print( "Current proc time {:.3f} ms, proc {:.3f} mps".format(proc_time_avg*1000.0, 1.0/proc_time_avg) )
    old_det_objects = new_det_objects

  client.loopStop()
  test_end_time = get_epoch_time()

  total_time = test_end_time - test_start_time
  total_rate = objects_detected / total_time

  if proc_time_count > 0:
    print( "Final rate incoming {:.3f} messages/ss".format(total_rate) )
    print( "Final proc time {:.3f} ms, proc {:.3f} mps".format(proc_time_avg*1000.0, 1.0/proc_time_avg) )
    result = 0
  else:
    print( "Unknown processing time" )

  if log_file is not None:
    log_file.close()

  return result

if __name__ == '__main__':
  exit(test_mqtt_recorder() or 0)
