#!/usr/bin/env python3

# Copyright (C) 2024 Intel Corporation
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
import time
import os
from tests.functional.backend_functional import BackendFunctionalTest
from scene_common.mqtt import PubSub
from scene_common import log

try:
  import psutil
except ImportError:
  import subprocess
  import sys
  subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
  # Make sure that if Python doesn't have the import directory in the search path, refresh it
  import site
  from importlib import reload
  reload(site)
  import psutil


TEST_NAME = "NEX-T10541"
TEST_WAIT_TIME = 2 * 60 * 60  # 2 hours in seconds

class REIDPerformanceDegradation(BackendFunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.vdms_connect()

    self.connected = False
    self.scenes_updates = {
      "3bc091c7-e449-46a0-9540-29c499bca18c": {
        "updated": False
      },
      "302cf49a-97ec-402d-a324-c5077b280b7b": {
        "updated": False
      }
    }
    self.performance_db = []

    self.client = PubSub(self.params["auth"], None, self.params["rootcert"], self.params["broker_url"])
    self.client.onConnect = self.on_connect
    for sc_uid in self.scenes_updates:
      self.client.addCallback(PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person"), self.on_scene_message)
    self.client.connect()
    self.client.loopStart()

  def on_connect(self, mqttc, data, flags, rc):
    """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
    @param    mqttc     The mqtt client object.
    @param    obj       The private user data.
    @param    flags     The response sent by the broker.
    @param    rc        The connection result.
    """
    self.connected = True
    log.info("Connected to MQTT Broker")
    for sc_uid in self.scenes_updates:
      topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person")
      mqttc.subscribe(topic, 0)
      log.info("Subscribed to the topic {}".format(topic))
    return

  def get_sys_info(self):
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/').percent
    return cpu_usage, memory_usage, disk_usage

  def get_vdms_time(self):
    start_time = time.time()
    self.get_similarity_comparison(20)
    end_time = time.time()
    return end_time - start_time

  def store_performance_results(self, test_time):
    cpu_usage, memory_usage, disk_usage = self.get_sys_info()
    vdms_time = self.get_vdms_time()
    self.performance_db.append([test_time, cpu_usage, memory_usage, disk_usage, vdms_time])
    log.info(f"{test_time}, {cpu_usage}, {memory_usage}, {disk_usage}, {vdms_time}")
    return

  def on_scene_message(self, mqttc, condlock, msg):
    real_msg = str(msg.payload.decode("utf-8"))
    json_data = json.loads(real_msg)

    # Verify that everything is still working as expected
    for scene in self.scenes_updates:
      if json_data['id'] == scene:
        self.scenes_updates[scene]["updated"] = True
    return

  def get_average_values(self, position):
    avg_elem_num = 5  # On how many elements we want to base the floor and ceiling
    first_elements_lists = self.performance_db[:avg_elem_num]
    last_elements_lists = self.performance_db[-avg_elem_num:]
    avg_first = sum([sublist[position] for sublist in first_elements_lists]) / len(first_elements_lists)
    avg_last = sum([sublist[position] for sublist in last_elements_lists]) / len(last_elements_lists)
    avg_complete = sum([sublist[position] for sublist in self.performance_db]) / len(self.performance_db)
    return(avg_first, avg_last, avg_complete)

  def check_returned_values(self):
    return_value = True

    cpu_averages = self.get_average_values(1)
    log.info(f"-> CPU: Start - {cpu_averages[0]}, End - {cpu_averages[1]}, Avg - {cpu_averages[2]}")
    if (cpu_averages[1] >= cpu_averages[0] * 1.2):
      log.error("The final CPU average shouldn't be 20% greater than the initial one!")
      return_value = False

    mem_averages = self.get_average_values(2)
    log.info(f"-> Memory: Start - {mem_averages[0]}, End - {mem_averages[1]}, Avg - {mem_averages[2]}")
    if (mem_averages[1] >= mem_averages[0] * 1.1):
      log.error("The final Memory average shouldn't be 10% greater than the initial one!")
      return_value = False

    disk_averages = self.get_average_values(3)
    log.info(f"-> Disk Usage: Start - {disk_averages[0]}, End - {disk_averages[1]}, Avg - {disk_averages[2]}")
    if (disk_averages[1] >= disk_averages[0] * 1.1):
      log.error("The final Disk Usage average shouldn't be 10% greater than the initial one!")
      return_value = False

    query_averages = self.get_average_values(4)
    log.info(f"-> Query time: Start - {query_averages[0]}, End - {query_averages[1]}, Avg - {query_averages[2]}")
    if (query_averages[1] >= query_averages[0] * 3):
      log.error("The final Query time average shouldn't be 3 times greater than the initial one!")
      return_value = False

    return return_value

  def check_perf_degradation(self):
    """! Verify that the system performance is stable while running
    @return  BOOL       True for the expected behaviour.
    """
    interval = 60  # seconds
    start_time = time.time()
    updated = False  # Compute only once the performance data

    log.info(f"The test will run for {TEST_WAIT_TIME} seconds and will print an update aproximately every {interval} seconds.")
    log.info("Timestamp, CPU Usage, Memory Usage, Disk Usage, Query time")

    while time.time() - start_time < TEST_WAIT_TIME:
      time.sleep(interval)
      time_interval = int(time.time() - start_time)
      for scene in self.scenes_updates:
        if self.scenes_updates[scene]["updated"] == True:
          updated = True
          self.scenes_updates[scene]["updated"] = False
        else:
          log.error(f"-> The {scene} scene hasn't sent any update in the past {interval} seconds! Aborting the test!")
          return False
      if updated:
        self.store_performance_results(time_interval)

    log.info("Calculate if there was any performance degradation...")
    return self.check_returned_values()

  def verifyThings(self):
    try:
      assert self.check_perf_degradation()
      self.client.loopStop()
      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

def test_reid_performance_degradation(request, record_xml_attribute):
  """! Test that the system hasn't suffered a significant performance degradation.
  @param    request                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """

  test = REIDPerformanceDegradation(TEST_NAME, request, record_xml_attribute)
  test.verifyThings()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_reid_performance_degradation(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
