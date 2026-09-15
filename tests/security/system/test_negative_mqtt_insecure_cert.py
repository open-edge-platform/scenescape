#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import ssl
import time

import tests.common_test_utils as common
from scene_common.mqtt import initializeMqttClient
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
import pytest

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=False, auth="",
)

TEST_WAIT_TIME = 10
connected = False

def on_connect(mqttc, obj, flags, rc):
  global connected
  if rc != 0:
    print( "Connection refused (rc={})".format( rc ) )
    return
  connected = True
  print( "Connected" )


@pytest.mark.test_name("NEX-T21777")
def test_mqtt_insecure_cert(scenescape_env):

  TEST_NAME = "NEX-T21777"

  print("Executing: " + TEST_NAME)

  # mqtt broker info:
  mqtt_broker = 'broker.scenescape.intel.com'
  mqtt_port = 1883

  client = initializeMqttClient()

  result = 1
  try:
    # Enable TLS with certificate verification enforced, but do NOT trust the
    # SceneScape CA. The broker presents a certificate signed by the private
    # SceneScape CA, which is not in the default system trust store, so a
    # secure client must reject it and fail to connect.
    client.tls_set()
    client.tls_insecure_set(False)

    client.on_connect = on_connect
    client.connect(mqtt_broker, mqtt_port, 60)

    client.loop_start()
    time.sleep( TEST_WAIT_TIME )
    client.loop_stop()

    global connected

    if connected:
      print( "Test failed! Connected with untrusted certificate!" )
    else:
      print( "Test passed! Untrusted certificate rejected, unable to connect!" )
      result = 0
  except (OSError, ssl.SSLError):
    print( "Test passed! Untrusted certificate rejected, unable to connect!" )
    result = 0

  common.record_test_result(TEST_NAME, result)

  assert result == 0

if __name__ == '__main__':
  exit( test_mqtt_insecure_cert() or 0 )
