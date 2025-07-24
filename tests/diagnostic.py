# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from argparse import ArgumentParser
import threading
import json

# FIXME - common_test_utils should be incorporated into the class, but
#         is still being used by older tests
import tests.common_test_utils as common

class Diagnostic:
  def __init__(self, testName, request, recordXMLAttribute):
    self.exitCode = 1
    self.testName = testName
    self.recordXMLAttribute = recordXMLAttribute

    parser = self.buildArgparser()
    if request is not None:
      # Filter pytest command line for any arguments that were provided
      defaults = {}
      for option in parser.arguments:
        val = request.config.getoption(option, default=None)
        if val is not None:
          defaults[option] = str(val)
      args = parser.parse_args([item for key in defaults for item in (key, defaults[key])])
    else:
      args = parser.parse_args()
    self.params = vars(args)
    return

  def buildArgparser(self):
    raise NotImplemented("Must be defined by subclass")

  def argumentParser(self):
    return SpecialParser()

  def _topicReceived(self, pahoClient, userdata, message):
    data = json.loads(message.payload.decode('utf-8'))
    if data is not None:
      print("Topic received", message.topic, data)
      self._topicCondition.acquire()
      self._topicCondition.notify()
      self._topicCondition.release()
    return

  def waitForTopic(self, waitTopic, timeout):
    """Waits for `waitTopic` to arrive or timeout is reached.

    @param      waitTopic       topic to subscribe to and wait for tracking data
    @param      timeout         seconds to wait before giving up
    @return                     True/False to indicate topic arrived in time
    """

    # It's up to subclass to create self.pubsub
    print("Waiting for ready", self.pubsub.isConnected(), waitTopic)
    self.pubsub.addCallback(waitTopic, self._topicReceived)

    ready = False
    self._topicCondition = threading.Condition()
    self._topicCondition.acquire()
    if self._topicCondition.wait(timeout):
      ready = True
    self._topicCondition.release()

    self.pubsub.removeCallback(waitTopic)

    return ready

  def recordTestResult(self):
    return common.record_test_result(self.testName, self.exitCode)

class SpecialParser(ArgumentParser):
  def add_argument(self, *args, **kwargs):
    for val in args:
      if isinstance(val, str) and len(val) and val[0] == '-' \
         and val not in ("-h", "--help"):
        if not hasattr(self, 'arguments'):
          self.arguments = []
        self.arguments.append(val)
    return super().add_argument(*args, **kwargs)
