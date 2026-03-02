#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Integration test for Reid data flow through the 2-tier architecture.
Tests the complete pipeline from detection ingestion through VDMS storage and retrieval.
"""

import base64
import json
import struct
import time
from unittest.mock import Mock
import numpy as np

import tests.common_test_utils as common
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from scene_common import log
from controller.vdms_adapter import VDMSDatabase, vdms


def create_reid_embedding():
  """Create a valid reid embedding vector."""
  embedding = np.random.rand(256).astype(np.float32)
  return embedding


def encode_reid_base64(embedding):
  """Encode reid embedding as base64 string."""
  packed = struct.pack('256f', *embedding)
  return base64.b64encode(packed).decode('utf-8')


def create_detection_message(camera_id, detections_data):
  """
  Create a mock detection message with optional metadata.

  @param camera_id  Camera identifier
  @param detections_data  List of tuples: (bbox, reid_data, semantic_data)
                          reid_data: (reid_embedding, model_name) or None
                          semantic_data: dict with semantic attributes or None
  @return Mock detection message in MQTT format
  """
  jdata = {
    "id": camera_id,
    "timestamp": get_iso_time(),
    "rate": 10.0,
    "objects": {
      "person": []
    }
  }

  for idx, (bbox, reid_data, semantic_data) in enumerate(detections_data):
    detection = {
      "id": idx + 1,
      "category": "person",
      "bounding_box_px": bbox  # Use pixel coordinates for reid extraction
    }

    # Add metadata if any is present
    if reid_data or semantic_data:
      detection["metadata"] = {}

      # Add reid if present
      if reid_data:
        reid_embedding, model_name = reid_data
        detection["metadata"]["reid"] = {
          "embedding_vector": encode_reid_base64(reid_embedding),
          "model_name": model_name
        }

      # Add semantic attributes if present
      if semantic_data:
        for key, value in semantic_data.items():
          detection["metadata"][key] = value

    jdata["objects"]["person"].append(detection)

  return jdata


def create_mock_mqtt_message(topic_str, payload_dict):
  """
  Create a mock MQTT message for testing.

  @param topic_str  MQTT topic string
  @param payload_dict  Message payload as dictionary
  @return Mock MQTT message object
  """
  mock_msg = Mock()
  mock_msg.topic = topic_str
  mock_msg.payload = Mock()
  mock_msg.payload.decode = Mock(return_value=json.dumps(payload_dict))
  return mock_msg


def wait_for_vdms_ready(use_tls=False, max_attempts=30, retry_interval=1):
  """
  Wait for VDMS to be ready by attempting to connect and query.

  @param use_tls  Whether to use TLS connection
  @param max_attempts  Maximum number of retry attempts
  @param retry_interval  Seconds to wait between retries
  @return True if VDMS is ready, False if timed out
  """
  for attempt in range(max_attempts):
    try:
      vdb = VDMSDatabase()
      if not use_tls:
        vdb.db = vdms.vdms(use_tls=False)
      vdb.connect()

      # Verify VDMS can handle queries
      query = [{
        "FindDescriptor": {
          "set": "reid_vector",
          "constraints": {
            "type": ["==", "person"]
          },
          "results": {
            "list": ["uuid"],
            "blob": False
          }
        }
      }]

      result = vdb.db.query(query)
      log.info(f"VDMS is ready (attempt {attempt + 1})")
      return True

    except Exception as e:
      log.debug(f"VDMS health check attempt {attempt + 1}/{max_attempts}: {e}")

    if attempt < max_attempts - 1:
      time.sleep(retry_interval)

  log.warning(f"VDMS not ready after {max_attempts} attempts")
  return False


def query_vdms_reid_count(camera_id, scene_uid, use_tls=True):
  """
  Query VDMS to count reid vectors stored for a specific camera/scene.
  The scene controller stores descriptors with properties: uuid, rvid, type.

  @param camera_id  Camera UUID (unused but kept for API compatibility)
  @param scene_uid  Scene UUID (unused but kept for API compatibility)
  @param use_tls    Whether to use TLS connection
  @return Number of reid vectors found
  """
  try:
    vdb = VDMSDatabase()
    if not use_tls:
      vdb.db = vdms.vdms(use_tls=False)
    vdb.connect()

    # Query for reid vectors by type constraint
    # The scene controller stores: uuid, rvid, type (not camera_id)
    query = [{
      "FindDescriptor": {
        "set": "reid_vector",
        "constraints": {
          "type": ["==", "person"]
        },
        "results": {
          "list": ["uuid", "rvid", "type"],
          "blob": False
        }
      }
    }]

    result = vdb.db.query(query)
    # VDMS query() returns (response, blob_array) tuple
    if isinstance(result, tuple) and len(result) == 2:
      response, _ = result
    else:
      log.error(f"VDMS query returned unexpected result type: "
                f"{type(result)}, value: {result}")
      return 0

    if response and len(response) > 0:
      find_result = response[0].get("FindDescriptor", {})
      entities = find_result.get("entities", [])
      log.info(f"VDMS query found {len(entities)} reid vectors "
               f"for camera {camera_id}")
      return len(entities)

    log.info(f"VDMS query found 0 reid vectors for camera {camera_id}")
    return 0

  except Exception as e:
    log.error(f"VDMS query failed: {e}")
    return 0


def setup_test_environment(params):
  """
  Setup common test environment: authenticate, get scene/camera, connect to MQTT.

  @param params  Test parameters from pytest fixture
  @return Tuple: (rest_client, scene_uid, scene_name, camera_id, pubsub, topic_str)
  """
  # Setup: Authenticate and get scene/camera info
  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  res = rest.authenticate(params['user'], params['password'])
  assert res, "Authentication failed"

  # Get a scene with cameras configured
  scenes_result = rest.getScenes({})
  assert scenes_result, "Failed to get scenes"
  assert len(scenes_result['results']) > 0, "No scenes available for testing"

  test_scene = scenes_result['results'][0]
  scene_uid = test_scene['uid']
  scene_name = test_scene['name']

  # Get cameras for the scene
  cameras_result = rest.getCameras({'scene': scene_uid})
  assert cameras_result, "Failed to get cameras"
  assert len(cameras_result['results']) > 0, "No cameras available for testing"

  test_camera = cameras_result['results'][0]
  camera_id = test_camera['uid']

  log.info(f"Testing with scene: {scene_name} ({scene_uid}), camera: {camera_id}")

  # Connect to MQTT broker to publish test messages
  mqtt_broker = params.get('broker_url', 'broker.scenescape.intel.com')
  mqtt_auth = params.get('auth')
  client_cert = params.get('client_cert')
  root_cert = params['rootcert']

  log.info(f"Connecting to MQTT broker: {mqtt_broker}")
  pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)

  # Wait for connection
  connected = False
  def on_connect(client, userdata, flags, rc):
    nonlocal connected
    connected = True
    log.info(f"Connected to MQTT broker with result code {rc}")

  pubsub.onConnect = on_connect
  pubsub.connect()
  pubsub.loopStart()

  # Wait for connection (up to 10 seconds)
  for i in range(100):
    if connected:
      break
    time.sleep(0.1)

  assert connected, "Failed to connect to MQTT broker"
  log.info("Successfully connected to MQTT broker")

  # Wait for VDMS to be ready using connection check
  log.info("Waiting for VDMS to be ready...")
  vdms_ready = wait_for_vdms_ready(use_tls=False, max_attempts=30, retry_interval=1)
  assert vdms_ready, "VDMS failed to become ready within timeout"
  log.info("VDMS is ready")

  # Ensure VDMS descriptor set exists
  log.info("Ensuring VDMS descriptor set exists...")
  vdb = VDMSDatabase()
  vdb.db.connect("vdms.scenescape.intel.com")
  if not vdb.findSchema("reid_vector"):
    log.info("Creating reid_vector descriptor set...")
    vdb.addSchema("reid_vector", "L2", 256)
    log.info("Descriptor set created successfully")
  else:
    log.info("Descriptor set already exists")

  topic_str = f"scenescape/data/camera/{camera_id}"
  return rest, scene_uid, scene_name, camera_id, pubsub, topic_str


def publish_detection_frames(pubsub, topic_str, detections_data, num_frames=25):
  """
  Publish multiple detection frames to establish tracking.

  @param pubsub  MQTT client
  @param topic_str  MQTT topic for publishing
  @param detections_data  List of detection tuples
  @param num_frames  Number of frames to publish
  """
  frame_interval = 0.1  # 10 FPS to match tracker config

  log.info(f"Publishing {num_frames} frames to topic: {topic_str}")
  for frame_num in range(num_frames):
    msg = create_detection_message(list(detections_data.keys())[0], detections_data[list(detections_data.keys())[0]])
    pubsub.publish(topic_str, json.dumps(msg))
    time.sleep(frame_interval)

  log.info(f"Published {num_frames} frames")


def trigger_track_pruning(pubsub, topic_str, camera_id):
  """
  Send empty frames and wait for track pruning and VDMS storage.

  @param pubsub  MQTT client
  @param topic_str  MQTT topic for publishing
  @param camera_id  Camera identifier
  """
  # Wait for similarity query to complete
  log.info("Waiting for similarity query to complete...")
  time.sleep(2)

  # Publish multiple empty frames to trigger track pruning
  log.info("Sending 10 empty frames to trigger track pruning...")
  for i in range(10):
    empty_msg = {
      "id": camera_id,
      "timestamp": get_iso_time(),
      "rate": 10.0,
      "objects": {"person": []}
    }
    pubsub.publish(topic_str, json.dumps(empty_msg))
    time.sleep(0.1)

  # Wait for timeout flush and VDMS insertion
  log.info("Waiting for stale feature timeout (5s) and VDMS storage (3s)...")
  time.sleep(8)


def test_reid_no_metadata(params, record_xml_attribute):
  """
  Test Reid data flow with NO metadata (baseline scenario).

  Validates that detection messages without metadata are processed correctly
  and no reid vectors are stored in VDMS.

  @param params  Test parameters from pytest fixture
  @param record_xml_attribute  Pytest fixture for recording test metadata
  """
  TEST_NAME = "NEX-T19883-NO-METADATA"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  exit_code = 1

  try:
    rest, scene_uid, scene_name, camera_id, pubsub, topic_str = setup_test_environment(params)

    log.info("=" * 80)
    log.info("SCENARIO 1: Testing with NO metadata")
    log.info("=" * 80)

    # Create detection without metadata
    detections_no_metadata = [
      ({"x": 100, "y": 100, "width": 100, "height": 200}, None, None)
    ]

    msg_no_metadata = create_detection_message(camera_id, detections_no_metadata)

    # Verify structure
    assert "objects" in msg_no_metadata
    assert "metadata" not in msg_no_metadata["objects"]["person"][0], \
           "Should have no metadata"

    log.info("✓ Message structure verified")

    # Publish message
    pubsub.publish(topic_str, json.dumps(msg_no_metadata))
    log.info(f"Published message to topic: {topic_str}")
    time.sleep(1)

    # Verify NO reid data stored
    reid_count = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    assert reid_count == 0, f"Expected 0 reid vectors, found {reid_count}"
    log.info("✓ VDMS verification passed: No reid vectors stored")

    log.info("✓ Test passed: No metadata flow validated")

    pubsub.loopStop()
    pubsub.disconnect()
    exit_code = 0

  except Exception as e:
    log.error(f"Test failed with exception: {e}")
    import traceback
    traceback.print_exc()
    raise

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0, "No metadata test failed"


def test_reid_only_metadata(params, record_xml_attribute):
  """
  Test Reid data flow with REID ONLY metadata (no semantic attributes).

  Validates that reid embeddings are correctly extracted, tracked, and stored
  in VDMS without semantic metadata.

  @param params  Test parameters from pytest fixture
  @param record_xml_attribute  Pytest fixture for recording test metadata
  """
  TEST_NAME = "NEX-T19883-REID-ONLY"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  exit_code = 1

  try:
    rest, scene_uid, scene_name, camera_id, pubsub, topic_str = setup_test_environment(params)

    log.info("=" * 80)
    log.info("SCENARIO 2: Testing with REID ONLY metadata")
    log.info("=" * 80)

    # Create embeddings
    embeddings = [create_reid_embedding(), create_reid_embedding()]

    # Create detection with reid only
    detections_reid_only = [
      ({"x": 100, "y": 100, "width": 100, "height": 200},
       (embeddings[0], "person-reidentification-retail-0287"),
       None),
      ({"x": 500, "y": 100, "width": 100, "height": 200},
       (embeddings[1], "person-reidentification-retail-0287"),
       None)
    ]

    msg_reid_only = create_detection_message(camera_id, detections_reid_only)

    # Verify structure
    for idx, det in enumerate(msg_reid_only["objects"]["person"]):
      assert "metadata" in det, f"Detection {idx}: Missing metadata"
      assert "reid" in det["metadata"], f"Detection {idx}: Missing reid"
      assert "age" not in det["metadata"], f"Detection {idx}: Should not have semantic metadata"

      reid = det["metadata"]["reid"]
      assert "embedding_vector" in reid, f"Detection {idx}: Missing embedding_vector"
      assert "model_name" in reid, f"Detection {idx}: Missing model_name"
      assert isinstance(reid["embedding_vector"], str), \
             f"Detection {idx}: embedding should be base64 string"
      assert len(reid["embedding_vector"]) > 1000, \
             f"Detection {idx}: embedding base64 string seems too short"

    log.info(f"✓ Message structure verified ({len(detections_reid_only)} detections with reid)")

    # Publish multiple frames to establish tracking
    num_frames = 25
    frame_interval = 0.1

    log.info(f"Publishing {num_frames} frames with reid metadata...")
    for frame_num in range(num_frames):
      msg_reid_only = create_detection_message(camera_id, detections_reid_only)
      pubsub.publish(topic_str, json.dumps(msg_reid_only))
      time.sleep(frame_interval)

    log.info(f"Published {num_frames} reid-only frames")

    # Trigger track pruning and VDMS storage
    trigger_track_pruning(pubsub, topic_str, camera_id)

    # Verify reid vectors stored
    reid_count = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    assert reid_count >= 2, f"Expected >= 2 reid vectors, found {reid_count}"
    log.info(f"✓ VDMS verification passed: {reid_count} reid vectors stored")

    log.info("✓ Test passed: Reid-only flow validated")

    pubsub.loopStop()
    pubsub.disconnect()
    exit_code = 0

  except Exception as e:
    log.error(f"Test failed with exception: {e}")
    import traceback
    traceback.print_exc()
    raise

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0, "Reid-only test failed"


def test_reid_semantic_only_metadata(params, record_xml_attribute):
  """
  Test Reid data flow with SEMANTIC ONLY metadata (no reid embeddings).

  Validates that semantic attributes (age, gender) are correctly processed
  and no NEW reid vectors are stored when reid data is absent.
  Note: This test is independent and does not rely on previous test state.

  @param params  Test parameters from pytest fixture
  @param record_xml_attribute  Pytest fixture for recording test metadata
  """
  TEST_NAME = "NEX-T19883-SEMANTIC-ONLY"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  exit_code = 1

  try:
    rest, scene_uid, scene_name, camera_id, pubsub, topic_str = setup_test_environment(params)

    log.info("=" * 80)
    log.info("SCENARIO 3: Testing with SEMANTIC ONLY metadata")
    log.info("=" * 80)

    # Capture current reid count before semantic-only test
    reid_count_before = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    log.info(f"VDMS reid vectors before semantic-only test: {reid_count_before}")

    # Define semantic metadata
    semantic_attrs = {
      "age": {"value": 28, "confidence": 0.85},
      "gender": {"value": "male", "confidence": 0.92}
    }

    # Create detection with semantic only
    detections_semantic_only = [
      ({"x": 100, "y": 100, "width": 100, "height": 200},
       None,
       semantic_attrs.copy())
    ]

    msg_semantic_only = create_detection_message(camera_id, detections_semantic_only)

    # Verify structure
    det = msg_semantic_only["objects"]["person"][0]
    assert "metadata" in det, "Missing metadata"
    assert "reid" not in det["metadata"], "Should not have reid"
    assert "age" in det["metadata"], "Missing age"
    assert "gender" in det["metadata"], "Missing gender"
    assert det["metadata"]["age"]["value"] == 28, "Age value incorrect"
    assert det["metadata"]["gender"]["value"] == "male", "Gender value incorrect"

    log.info("✓ Message structure verified (semantic attributes: age, gender)")

    # Publish message
    pubsub.publish(topic_str, json.dumps(msg_semantic_only))
    log.info(f"Published semantic-only message to topic: {topic_str}")
    time.sleep(2)

    # Verify NO NEW reid vectors stored (semantic only, no reid)
    # VDMS is persistent, so we check that count doesn't increase
    reid_count_after = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    log.info(f"VDMS reid vectors after semantic-only test: {reid_count_after}")
    assert reid_count_after == reid_count_before, \
           f"Expected no new reid vectors (before={reid_count_before}, after={reid_count_after})"
    log.info(f"✓ VDMS verification passed: No new reid vectors stored ({reid_count_before} total)")

    log.info("✓ Test passed: Semantic-only flow validated")

    pubsub.loopStop()
    pubsub.disconnect()
    exit_code = 0

  except Exception as e:
    log.error(f"Test failed with exception: {e}")
    import traceback
    traceback.print_exc()
    raise

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0, "Semantic-only test failed"


def test_reid_combined_metadata(params, record_xml_attribute):
  """
  Test Reid data flow with REID + SEMANTIC metadata (complete metadata).

  Validates that reid embeddings and semantic attributes are correctly
  processed together and stored in VDMS with full metadata.

  @param params  Test parameters from pytest fixture
  @param record_xml_attribute  Pytest fixture for recording test metadata
  """
  TEST_NAME = "NEX-T19883-COMBINED"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  exit_code = 1

  try:
    rest, scene_uid, scene_name, camera_id, pubsub, topic_str = setup_test_environment(params)

    log.info("=" * 80)
    log.info("SCENARIO 4: Testing with REID + SEMANTIC metadata")
    log.info("=" * 80)

    # Create embeddings and semantic metadata
    embeddings = [create_reid_embedding(), create_reid_embedding()]
    semantic_attrs = {
      "age": {"value": 28, "confidence": 0.85},
      "gender": {"value": "male", "confidence": 0.92}
    }

    # Create detection with both reid and semantic
    detections_combined = [
      ({"x": 100, "y": 100, "width": 100, "height": 200},
       (embeddings[0], "person-reidentification-retail-0287"),
       semantic_attrs.copy()),
      ({"x": 500, "y": 100, "width": 100, "height": 200},
       (embeddings[1], "person-reidentification-retail-0287"),
       {"age": {"value": 35, "confidence": 0.78}, "gender": {"value": "female", "confidence": 0.88}})
    ]

    msg_combined = create_detection_message(camera_id, detections_combined)

    # Verify structure for both detections
    for idx, det in enumerate(msg_combined["objects"]["person"]):
      assert "metadata" in det, f"Detection {idx}: Missing metadata"
      assert "reid" in det["metadata"], f"Detection {idx}: Missing reid"
      assert "age" in det["metadata"], f"Detection {idx}: Missing age"
      assert "gender" in det["metadata"], f"Detection {idx}: Missing gender"

      # Verify reid structure
      reid = det["metadata"]["reid"]
      assert "embedding_vector" in reid, f"Detection {idx}: Missing embedding_vector"
      assert "model_name" in reid, f"Detection {idx}: Missing model_name"
      assert isinstance(reid["embedding_vector"], str), \
             f"Detection {idx}: embedding should be base64 string"
      assert len(reid["embedding_vector"]) > 1000, \
             f"Detection {idx}: embedding base64 string seems too short"

      # Verify semantic structure
      assert "value" in det["metadata"]["age"], f"Detection {idx}: age missing value"
      assert "confidence" in det["metadata"]["age"], f"Detection {idx}: age missing confidence"

    log.info(f"✓ Message structure verified ({len(detections_combined)} detections with reid+semantic)")

    # Publish multiple frames to establish tracking
    num_frames = 25
    frame_interval = 0.1

    log.info(f"Publishing {num_frames} frames with reid+semantic metadata...")
    for frame_num in range(num_frames):
      msg_combined = create_detection_message(camera_id, detections_combined)
      pubsub.publish(topic_str, json.dumps(msg_combined))
      time.sleep(frame_interval)

    log.info(f"Published {num_frames} combined reid+semantic frames")

    # Trigger track pruning and VDMS storage
    trigger_track_pruning(pubsub, topic_str, camera_id)

    # Verify reid vectors stored
    reid_count = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    assert reid_count >= 2, f"Expected >= 2 reid vectors, found {reid_count}"
    log.info(f"✓ VDMS verification passed: {reid_count} reid vectors stored")

    log.info("✓ Test passed: Combined reid+semantic flow validated")

    pubsub.loopStop()
    pubsub.disconnect()
    exit_code = 0

  except Exception as e:
    log.error(f"Test failed with exception: {e}")
    import traceback
    traceback.print_exc()
    raise

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0, "Combined metadata test failed"
