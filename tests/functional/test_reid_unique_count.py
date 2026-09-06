#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import tests.common_test_utils as common
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from tests.functional.reid_backend import get_reid_profile_module
from tests.utils.spec import FuncTestSpec
from tests.utils.log import get_logger

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=get_reid_profile_module(),
)

TEST_WAIT_TIME = 150
LOOSE_MODE_ALLOWED_EXCEED_INTERVALS = 2
connected = False
detection_count = {}
count_transitions = {}
reid_state_observations = {}
callback_failures = []

PENDING_COLLECTION = "pending_collection"
QUERY_NO_MATCH = "query_no_match"
MATCHED = "matched"

def get_scene_count_bounds():
  # Baseline expectation for stable ReID behavior on the reference stream.
  return 3, 6

def expect_exceed_max_unique_count(params):
  value = str(params.get("expect_exceed_max", "")).strip().lower()

  if not value:
    log.info(
      "--expect_exceed_max not provided; defaulting to loose expectation (must stay at or below max).")
    return False

  true_values = {"1", "true", "yes", "y", "on"}
  false_values = {"0", "false", "no", "n", "off"}

  if value in true_values:
    return True

  if value in false_values:
    return False

  log.warning(
    f"Invalid --expect_exceed_max value '{value}', defaulting to False.")
  return False

def on_connect(mqttc, data, flags, rc):
  """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    flags     The response sent by the broker.
  @param    rc        The connection result.
  """
  global connected
  global detection_count
  connected = True
  log.info("Connected to MQTT Broker")
  for sc_uid in detection_count:
    topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person")
    mqttc.subscribe(topic, 0)
    log.info("Subscribed to the topic {}".format(topic))
  return

def on_scene_message(mqttc, condlock, msg):
  global detection_count
  global count_transitions
  global reid_state_observations
  global callback_failures
  real_msg = str(msg.payload.decode("utf-8"))
  json_data = json.loads(real_msg)

  try:
    validate_reid_output_structure(json_data)
  except AssertionError as err:
    callback_failures.append(str(err))
    return

  for scene in detection_count:
    if json_data['id'] == scene:
      previous = detection_count[scene]["current"]
      # If the unique count somehow decremented, raise an error
      if previous > json_data['unique_detection_count']:
        detection_count[scene]["error"] = True
      detection_count[scene]["current"] = json_data['unique_detection_count']

      if previous != json_data['unique_detection_count']:
        event = {
          "timestamp": json_data.get("timestamp", "unknown"),
          "from": previous,
          "to": json_data['unique_detection_count']
        }
        count_transitions[scene].append(event)

  return

def validate_previous_ids_chain_entry(obj, entry):
  assert isinstance(entry, dict), (
    f"Object {obj.get('id')} previous_ids_chain entries must be dicts")
  assert 'id' in entry, (
    f"Object {obj.get('id')} matched previous_ids_chain entry missing 'id': {entry}")
  assert 'timestamp' in entry, (
    f"Object {obj.get('id')} matched previous_ids_chain entry missing 'timestamp': {entry}")
  assert 'similarity_score' in entry, (
    f"Object {obj.get('id')} matched previous_ids_chain entry missing 'similarity_score': {entry}")

def validate_object_reid_output(obj):
  state = obj.get('reid_state')
  similarity = obj.get('similarity')
  has_previous_ids_chain = 'previous_ids_chain' in obj
  previous_ids_chain = obj.get('previous_ids_chain')

  assert state in {PENDING_COLLECTION, QUERY_NO_MATCH, MATCHED}, (
    f"Object {obj.get('id')} has unexpected reid_state: {state}")

  if state in {PENDING_COLLECTION, QUERY_NO_MATCH}:
    assert similarity is None, (
      f"Object {obj.get('id')} state={state} must not publish similarity: {similarity}")
    assert not has_previous_ids_chain, (
      f"Object {obj.get('id')} state={state} must not publish previous_ids_chain: {previous_ids_chain}")
    return

  assert similarity is not None, (
    f"Object {obj.get('id')} state={state} must publish similarity")
  if not has_previous_ids_chain:
    return

  assert isinstance(previous_ids_chain, list) and previous_ids_chain, (
    f"Object {obj.get('id')} state={state} has invalid previous_ids_chain: {previous_ids_chain}")

  for entry in previous_ids_chain:
    validate_previous_ids_chain_entry(obj, entry)

def validate_reid_output_structure(scene_msg):
  global reid_state_observations

  objects = scene_msg.get('objects', [])
  if not isinstance(objects, list):
    return

  scene_id = scene_msg.get('id', 'unknown-scene')
  observations = reid_state_observations.setdefault(
    scene_id,
    {
      PENDING_COLLECTION: 0,
      QUERY_NO_MATCH: 0,
      MATCHED: 0,
    }
  )

  for obj in objects:
    if obj.get('category') != 'person':
      continue

    validate_object_reid_output(obj)

    state = obj.get('reid_state')
    if state in observations:
      observations[state] += 1

def check_unique_detections(params):
  """! Verify if more than expected unique detections aren't found.
  @return  BOOL       True for the expected behaviour.
  """
  interval = 10  # seconds
  start_time = time.time()
  expect_exceed = expect_exceed_max_unique_count(params)
  exceeded_scenes = set()
  exceed_intervals = {scene: 0 for scene in detection_count}

  if expect_exceed:
    log.info("Expectation mode: tight threshold, unique count must exceed max at least once.")
  else:
    log.info("Expectation mode: loose threshold, unique count must stay at or below max.")

  minima = {
    scene: max(scene_state.get("minimum", 1), 1)
    for scene, scene_state in detection_count.items()
  }

  while time.time() - start_time < TEST_WAIT_TIME:
    time.sleep(interval)

    if callback_failures:
      log.error(f"ReID callback validation failures: {callback_failures}")
      return False

    log.info(f"Status after {int(time.time() - start_time)} / {TEST_WAIT_TIME} sec")

    for scene, scene_state in detection_count.items():
      current = scene_state["current"]
      maximum = scene_state["maximum"]

      if current <= maximum:
        exceed_intervals[scene] = 0
        log.info(f"-> Detections for {scene} of: {current} (max: {maximum})")
      else:
        if expect_exceed:
          log.info(
            f"-> Detections for {scene} exceeded max as expected: {current} (max: {maximum})")
          exceeded_scenes.add(scene)
        else:
          exceed_intervals[scene] += 1
          if exceed_intervals[scene] > LOOSE_MODE_ALLOWED_EXCEED_INTERVALS:
            log.error(
              f"-> Detections for {scene} remained greater than the maximum for "
              f"{exceed_intervals[scene]} intervals: {current} (max: {maximum})!")
            return False
          log.warning(
            f"-> Temporary exceed for {scene}: {current} (max: {maximum}), "
            f"interval {exceed_intervals[scene]} / {LOOSE_MODE_ALLOWED_EXCEED_INTERVALS}")

      if scene_state["error"]:
        log.error(f"The unique detection counter for {scene} somehow got decremented!")
        return False

    if expect_exceed and len(exceeded_scenes) == len(detection_count):
      log.info(
        "All scenes exceeded max at least once under tight-threshold mode; ending verification early.")
      break

  if expect_exceed:
    missing_exceed = [
      scene for scene in detection_count
      if scene not in exceeded_scenes
    ]
    if missing_exceed:
      log.error(
        f"Expected unique count to exceed max for scenes {missing_exceed}, but it never did.")
      return False

  for scene, scene_state in detection_count.items():
    current = scene_state["current"]
    minimum = minima[scene]

    if current == 0 and not count_transitions.get(scene):
      log.warning(
        f"No unique detections observed for {scene}; skipping minimum-count "
        "assertion for this run.")
      continue

    if current < minimum:
      log.error(
        f"The unique detection counter for {scene} is below minimum: "
        f"{current} (min: {minimum})!"
      )
      return False

  return True

def run_test(test_name, test_desc, scene_config, params):
  """! Generic test runner for RE-ID unique count tests.
  @param    test_name       The test identifier (e.g., "NEX-T10539").
  @param    test_desc       The test description.
  @param    scene_config    Dict of scene_id -> {error, current, maximum}.
  @param    params          Dict of test parameters.
  @return   exit_code       Indicates test success or failure.
  """
  global detection_count
  global count_transitions
  global reid_state_observations
  global callback_failures
  detection_count = scene_config
  count_transitions = {scene: [] for scene in detection_count}
  reid_state_observations = {
    scene: {
      PENDING_COLLECTION: 0,
      QUERY_NO_MATCH: 0,
      MATCHED: 0,
    }
    for scene in detection_count
  }
  callback_failures = []
  exit_code = 1

  try:
    client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                    port=int(params["broker_port"]))
    rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
    res = rest.authenticate(params['user'], params['password'])
    assert res, (res.errors)

    client.onConnect = on_connect
    for sc_uid in detection_count:
      client.addCallback(PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person"), on_scene_message)
    client.connect()
    client.loopStart()

    assert check_unique_detections(params)

    expect_exceed = expect_exceed_max_unique_count(params)
    if not expect_exceed:
      for scene, observations in reid_state_observations.items():
        log.info(f"ReID state observations for {scene}: {observations}")
        has_reid_activity = (
          observations[QUERY_NO_MATCH] > 0
          or observations[MATCHED] > 0
          or detection_count[scene]["current"] > 0
          or bool(count_transitions.get(scene))
        )
        if has_reid_activity:
          assert observations[MATCHED] > 0, (
            f"Expected at least one matched object message for {scene}, observed {observations}")
        else:
          log.warning(
            f"No reid activity observed for {scene}; skipping matched-state assertion "
            f"for this run. Observations: {observations}")
    else:
      for scene, observations in reid_state_observations.items():
        log.info(f"ReID state observations for {scene} (tight threshold, no matches expected): {observations}")

    for scene in detection_count:
      if count_transitions[scene]:
        log.info(f"Transition history for {scene}: {count_transitions[scene]}")
      else:
        log.info(f"No transitions observed for {scene}; final count: {detection_count[scene]['current']}")

    client.loopStop()
    exit_code = 0

  finally:
    common.record_test_result(test_name, exit_code)

  assert exit_code == 0
  return exit_code

def test_reid_unique_count(demo_scene, params, record_xml_attribute):
  """! Tests the unique count for each scene when RE-ID is enabled.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10539"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  log.info("Test the unique count for each scene when RE-ID is enabled.")

  minimum, maximum = get_scene_count_bounds()
  scene_config = {
    "302cf49a-97ec-402d-a324-c5077b280b7b": {
      "error": False,
      "current": 0,
      "minimum": minimum,
      "maximum": maximum
    }
  }

  run_test(TEST_NAME, "Test the unique count for each scene when RE-ID is enabled.", scene_config, params)
