#!/usr/bin/env python3

# Copyright (C) 2021-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import copy
import time
from datetime import datetime, timedelta

from scene_common.mqtt import PubSub
from tests.ui.browser import Browser
import tests.common_test_utils as common

TEST_NAME="NEX-T10411"

### How often to report out and compute how the test is going.
TEST_WAIT_TIME = 30

### How many messages should we receive. This is close to FPS * number of models
TEST_MIN_MESSAGES = TEST_WAIT_TIME * 2

### Maximum difference allowed for the sensor objects (higher vs lower).
### This is intended to check all streams are flowing at approx the same rate
TEST_MAX_OBJECT_VARIATION = 20

### Maximum difference allowed for the sensor objects (current FPS vs average FPS).
### This is intended to check if streams stutter or suddenly stop.
TEST_MAX_FPS_VARIATION = 10

objects_detected = 0
connected = False
test_started = False
sensor_list = {}
model_list = {}
num_sensors = 0
num_models = 0

class MQTTParams():
  """! Contains the tests MQTT parameters. """
  def __init__(self):
    """! Initialize the MQTTParams object.
    @return   None.
    """
    self.rootca = "/run/secrets/certs/scenescape-ca.pem"
    self.auth = "/run/secrets/percebro.auth"
    self.mqtt_broker = 'broker.scenescape.intel.com'
    self.mqtt_port = 1883
    return None

class SensorState():
  """! Contains the state and state update methods for a single sensor. """
  def __init__(self, model, sensor, model_avg_fps, model_cur_fps):
    """! Initialize the SensorState object.
    @param    model                   String naming the model the sensor is being used in.
    @param    sensor                  String sensor name.
    @param    model_avg_fps           List of model sensors average fps in milliseconds.
    @param    model_cur_fps           List of model sensors current fps in milliseconds.
    @return   None.
    """
    self.model = model
    self.sensor = sensor
    self.m_s_current = model_cur_fps[self.sensor]
    self.m_s_average = model_avg_fps[self.sensor]
    self.m_s_deviation = abs(self.m_s_average - self.m_s_current)
    self.variation_in_sensor_fps = False
    return None

  def error_in_fps_variation(self):
    """! Determines if fps variation is larger than TEST_MAX_FPS_VARIATION.
    @return   Bool                    True if variation in fps is large, otherwise false.
    """
    return self.m_s_deviation > TEST_MAX_FPS_VARIATION

  def check_variation_in_sensor_fps(self, state):
    """! Checks for variation in sensor fps.
    @param    state                   TestState object.
    @return   None.
    """
    if state.running_time.seconds > 120 and self.error_in_fps_variation():
      self.variation_in_sensor_fps = True
    return None

  def print_sensor_msg(self):
    """! Prints the current sensor state.
    @return   None.
    """
    print("Model {} Sensor {} has unexpected current {:.2f} average {:.2f}".format(self.model, self.sensor, self.m_s_deviation, self.m_s_current, self.m_s_average))
    return None

class TestState():
  """! Contains the tests current state. """
  def __init__(self, params):
    """! Initialize the TestState object.
    @param    params                  Dict of test parameters.
    @return   None.
    """
    self.params = params
    self.start_time = None
    self.end_time = None
    self.now_time = None
    self.remaining_time = None
    self.running_time = None
    self.test_time_hrs = None
    self.test_time_secs = None
    self.current_cycle = 0
    self.done = False
    self.variation_in_fps = False
    self.min_fps = TEST_WAIT_TIME * 100
    self.max_fps = 0
    return None

  def update_now_time(self):
    """! Sets now_time equal to the current system time.
    @return   None.
    """
    self.now_time = datetime.now()
    return None

  def set_start_end_time(self):
    """! Sets tests start and end time.
    @return   None.
    """
    self.update_now_time()
    self.start_time = self.now_time
    self.end_time = self.now_time + timedelta(seconds=self.test_time_secs)
    return None

  def update_running_remaining_time(self):
    """! Update test running_time and remaining_time.
    @return   None.
    """
    self.remaining_time = self.end_time - self.now_time
    self.running_time = self.now_time - self.start_time
    return None

  def get_test_time(self):
    """! Get test length and set related variables.
    @return   Bool                  True if valid time otherwise false.
    """
    self.test_time_hrs = float(self.params['hours'])
    if (self.test_time_hrs <= 0) or (self.test_time_hrs >= (24*7)):
      print("Need a valid test run time")
      return False
    self.test_time_secs = (self.test_time_hrs * 60 * 60)
    return True

  def update_min_max_fps(self, model_sensor_count):
    """! Update the min and max number of MQTT messages scenescape received from a sensor containing an image frame.
    @param    model_sensor_count    Int count of sensor frames received.
    @return   None.
    """
    self.min_fps = min(self.min_fps, model_sensor_count)
    self.max_fps = max(self.max_fps, model_sensor_count)
    return None

  def print_update(self):
    """! Print test update.
    @return   None.
    """
    percentageRun = (self.running_time.seconds / self.test_time_secs) * 100
    print()
    print("[{:.02f}% at {}] Runtime elapsed {} remaining {} (ending at {})".format(percentageRun, self.now_time.strftime("%c"), \
          str(self.running_time), str(self.remaining_time), self.end_time.strftime("%c")))
    print("{} Objects detected in last {} seconds (Min {} Max {})".format(objects_detected, TEST_WAIT_TIME, self.min_fps, self.max_fps))
    return None

  def login_failed(self):
    """! Checks that a browser is able to login to scenescape's web UI.
    @return   login_fail           Bool True if login failed, otherwise false.
    """
    login_fail = True
    browser = Browser()
    if browser.login(self.params['user'], self.params['password'], self.params['weburl']):
      login_fail = False
    else:
      print("Test browser login failed!")
    browser.close()
    return login_fail

  def enough_messages(self):
    """! Checks that the test has received enough sensor messages.
    @return   check_failed            Bool True if enough messages, otherwise False.
    """
    check_failed = False
    if (self.min_fps < TEST_MIN_MESSAGES):
      print("Test failed to receive enough messages!. Seems stuck at time {} (min {})".format(str(self.running_time), self.min_fps))
      check_failed = True
    return check_failed

  def stable_messages(self):
    """! Checks that the tests sensor message frequency is stable.
    @return   check_failed            Bool True if a sensor message frequency varies enough, otherwise False.
    """
    check_failed = False
    if (self.variation_in_fps == True):
      print("Test failed stable message check!. Seems stuck at time {} (variation {})".format(str(self.running_time), self.variation_in_fps))
      check_failed = True
    return check_failed

  def check_time_remaining(self):
    """! Checks if the test is finished.
    @return   Bool                    True if time remains, False otherwise.
    """
    return (self.remaining_time.seconds > 0) and (self.remaining_time.days >= 0)

def handle_mqtt_sensor_topic(msg):
  """! Count frames corresponding the MQTT messages received.
  @param    msg                     MQTT message object.
  @return   None.
  """
  global model_list
  global num_models
  topic_split = msg.topic.split('/')
  objects = msg.payload.decode('utf-8')['objects']
  if objects=={}:
    return None
  for category in objects:
    model = category
    sensor = topic_split[3]
    if model not in model_list:
      model_list[model] = {}
      num_models += 1
    if sensor not in model_list[model]:
      model_list[model][sensor] = 0
    model_list[model][sensor] += 1
  return None

def setup_mqtt_client(mqtt_params):
  """! Sets up and returns an MQTT client connected to the broker.
  @param    mqtt_params             MQTTParams object.
  @return   client                  Connected MQTT client.
  """
  client = PubSub(mqtt_params.auth, None, mqtt_params.rootca,
                  mqtt_params.mqtt_broker, mqtt_params.mqtt_port)
  client.onMessage = on_message
  client.onConnect = on_connect
  client.connect()
  return client

def update_sensor_avg_fps(model, model_avg_fps, model_cur_fps, state):
  """! Update the average fps given the fps of a models sensors over the current MQT message collection period.
  @param    model                   String model name.
  @param    model_avg_fps           Dict updated average fps over the test running time in the form [model][sensor].
  @param    model_cur_fps           Dict fps over the last MQTT message collection period in the form [model][sensor].
  @param    state                   TestState object.
  @return   state                   Updated TestState object.
  """
  for sensor in model_avg_fps:
    sensor_state = SensorState(model, sensor, model_avg_fps, model_cur_fps)
    sensor_state.check_variation_in_sensor_fps(state)
    if sensor_state.variation_in_sensor_fps:
      sensor_state.print_sensor_msg()
      state.variation_in_fps = True
  return state

def update_model_avg_fps(model_avg_fps, model_cur_fps, current_cycle):
  """! Updates model_avg_fps string with sensor state.
  @param    model_cur_fps           Dict fps over the last MQTT message collection period in the form [model][sensor].
  @param    current_cycle           Tests current cycle.
  @return   None.
  """
  for sensor in model_avg_fps:
    model_avg_fps[sensor] = (model_avg_fps[sensor] * (current_cycle-1)) + model_cur_fps[sensor]
    model_avg_fps[sensor] /= (current_cycle)
  return None

def update_avg_msg(avg_fps, state):
  """! Updates avg_msg string with sensor state.
  @param    avg_fps                 Dict updated average fps over the test running time in the form [model][sensor].
  @param    state                   TestState object.
  @return   avg_msg                 String updated average fps per model and sensor.
  """
  avg_msg = ""
  if state.current_cycle != 0:
    avg_msg = "AVG model/stream fps: "
    for model in avg_fps:
      for sensor in avg_fps[model]:
        avg_msg += "{}:{} at {:.2f} ".format(model, sensor,avg_fps[model][sensor])
  return avg_msg

def update_avg_fps(avg_fps, cur_fps, state):
  """! Update the average fps given the fps of all models over the current MQTT message collection period.
  @param    avg_fps                 Dict average fps over the test running time in the form [model][sensor].
  @param    cur_fps                 Dict fps over the last MQTT message collection period in the form [model][sensor].
  @param    state                   TestState object.
  @return   ave_msg                 String updated average fps per model and sensor.
  @return   state                   Updated TestState object.
  """
  if state.current_cycle != 0:
    for model in avg_fps:
      model_avg_fps = avg_fps[model]
      model_cur_fps = cur_fps[model]
      state = update_sensor_avg_fps(model, model_avg_fps, model_cur_fps, state)
      update_model_avg_fps(model_avg_fps, model_cur_fps, state.current_cycle)
  else:
    avg_fps = copy.deepcopy(cur_fps)
  return avg_fps, state

def get_current_fps_stats(model_list, state):
  """! Get FPS for the MQTT messages collected over the last collection period.
  @param    model_list              Dict of models and sensors in the form [model][sensor].
  @param    state                   TestState object.
  @return   cur_fps                 Dict fps over the last MQTT message collection period in the form [model][sensor].
  @return   state                   Updated TestState object.
  """
  cur_fps = {}
  for model in model_list:
    cur_fps[model] = {}
    for sensor in model_list[model]:
      model_sensor_count = model_list[model][sensor]
      cur_fps[model][sensor] = (model_sensor_count) / TEST_WAIT_TIME
      state.update_min_max_fps(model_sensor_count)
      model_list[model][sensor] = 0
  return cur_fps, state

def collect_mqtt_msgs(client):
  """! Collects MQTT messages using callback method on_message().
  @param    client                  MQTT client.
  @return   None.
  """
  client.loopStart()
  time.sleep(TEST_WAIT_TIME)
  client.loopStop()
  return None

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
  print( "Connected" )
  topic = 'scenescape/#'
  mqttc.subscribe( topic, 0)
  return None

def on_message(mqttc, obj, msg):
  """! Call back function for the MQTT client on receiving messages, counts frames received from each sensor.
  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    msg       The instance of MQTTMessage.
  @return   None.
  """
  global objects_detected
  global test_started
  if test_started == False :
    print( "First msg received (Topic {})".format( msg.topic ) )
    test_started = True
  topic = PubSub.parseTopic(msg.topic)
  if topic['_topic_id'] == PubSub.DATA_CAMERA:
    handle_mqtt_sensor_topic(msg)
  objects_detected += 1
  return

def test_sscape_stability(params, record_xml_attribute):
  """! Checks that scenescape performs as expected over a given time period.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   result                  Int 0 if test passed otherwise 1.
  """
  global connected
  global objects_detected
  global model_list
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)
  print("Trying user {} password {}".format(params['user'], params['password']))
  mqtt_params = MQTTParams()
  state = TestState(params)
  result = 1
  avg_fps = {}

  assert state.get_test_time()
  state.set_start_end_time()
  client = setup_mqtt_client(mqtt_params)
  collect_mqtt_msgs(client)
  assert connected

  print("Test starting at {}".format(state.start_time.strftime("%c")))
  print("Running for {} hours".format(state.test_time_hrs))
  print("End at {}".format(state.end_time.strftime("%c")))
  while (state.done == False):
    objects_detected = 0
    collect_mqtt_msgs(client)
    state.update_now_time()
    state.update_running_remaining_time()

    if state.check_time_remaining():
      cur_fps, state = get_current_fps_stats(model_list, state)
      state.print_update()
      avg_fps, state = update_avg_fps(avg_fps, cur_fps, state)
      avg_msg = update_avg_msg(avg_fps, state)

      if state.enough_messages() or state.stable_messages() or state.login_failed():
        state.done = True
      else:
        print(avg_msg, " log-in ok")
        state.current_cycle += 1
    else:
      state.done = True
      result = 0
      print("Test passed! {} of runtime".format(str(state.running_time)))

  common.record_test_result(TEST_NAME, result)
  assert result == 0
  return result
