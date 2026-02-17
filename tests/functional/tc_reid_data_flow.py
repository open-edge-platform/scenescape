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
from unittest.mock import Mock, patch, MagicMock
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


def test_reid_data_flow_end_to_end(params, record_xml_attribute):
  """
  Test complete Reid data flow from detection message to VDMS storage.

  This test validates the complete reid pipeline through 4 metadata scenarios:
  1. No metadata - baseline detection without any metadata
  2. Reid only - detection with reid embeddings but no semantic attributes
  3. Semantic only - detection with semantic attributes (age, gender) but no reid
  4. Reid + Semantic - complete metadata with both reid and semantic attributes

  For each scenario, this test validates:
  - Detection message ingestion through handleMovingObjectMessage
  - MovingObject extraction from metadata structure
  - UUID Manager processing and feature gathering
  - VDMS Adapter storage with correct metadata structure
  - VDMS query and retrieval of stored data

  @param params  Test parameters from pytest fixture
  @param record_xml_attribute  Pytest fixture for recording test metadata
  """
  TEST_NAME = "NEX-T10540"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  log.info("Test Reid data flow through 2-tier architecture")

  exit_code = 1

  try:
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
    pubsub.loopStart()  # Start MQTT client loop in background thread

    # Wait for connection (up to 10 seconds)
    for i in range(100):
      if connected:
        break
      time.sleep(0.1)

    assert connected, "Failed to connect to MQTT broker"
    log.info("Successfully connected to MQTT broker")

    # Wait for scene controller to be ready and VDMS connection to initialize
    # Controller needs time to: connect to MQTT, subscribe to camera topics,
    # initialize VDMS connection for reid storage (~30-35 seconds total)
    log.info("Waiting for scene controller and VDMS to initialize...")
    time.sleep(40)
    log.info("Scene controller initialization wait complete")

    # Ensure VDMS descriptor set exists before running tests
    # This handles first-time setup where the reid_vector set needs to be created
    log.info("Ensuring VDMS descriptor set exists...")
    vdb = VDMSDatabase()
    vdb.db.connect("vdms.scenescape.intel.com")
    if not vdb.findSchema("reid_vector"):
      log.info("Creating reid_vector descriptor set...")
      vdb.addSchema("reid_vector", "L2", 256)
      log.info("Descriptor set created successfully")
    else:
      log.info("Descriptor set already exists")

    # Subscribe to scene output to capture controller responses
    received_scene_messages = []
    def on_scene_message(client, userdata, msg):
      try:
        data = json.loads(msg.payload.decode())
        received_scene_messages.append(data)
        # Handle both dict and list formats for objects
        objects = data.get('objects', {})
        if isinstance(objects, dict):
          obj_count = len(objects.get('person', []))
        elif isinstance(objects, list):
          obj_count = len([o for o in objects if o.get('category') == 'person'])
        else:
          obj_count = 0
        log.info(f"Received scene output message with {obj_count} person objects")
      except Exception as e:
        log.error(f"Error parsing scene message: {e}")

    scene_output_topic = f"scenescape/data/scene/{scene_uid}/person"
    pubsub.addCallback(scene_output_topic, on_scene_message)
    log.info(f"Subscribed to scene output topic: {scene_output_topic}")

    # Create test data: Multiple embeddings for reid tests
    embeddings = [
      create_reid_embedding(),
      create_reid_embedding(),
      create_reid_embedding(),
      create_reid_embedding()
    ]

    # Define semantic metadata for tests
    semantic_attrs = {
      "age": {"value": 28, "confidence": 0.85},
      "gender": {"value": "male", "confidence": 0.92}
    }

    # =========================================================================
    # SCENARIO 1: No metadata
    # =========================================================================
    log.info("=" * 80)
    log.info("SCENARIO 1: Testing with NO metadata")
    log.info("=" * 80)

    # Use pixel coordinates: area = 100*200 = 20000 pixels (exceeds 5000 minimum)
    detections_no_metadata = [
      ({"x": 100, "y": 100, "width": 100, "height": 200}, None, None)
    ]

    msg_no_metadata = create_detection_message(camera_id, detections_no_metadata)

    # Verify structure
    assert "objects" in msg_no_metadata
    assert "metadata" not in msg_no_metadata["objects"]["person"][0], \
           "Scenario 1: Should have no metadata"

    log.info("✓ Scenario 1 message structure verified")

    # Publish message to MQTT broker for controller to process
    topic_str = f"scenescape/data/camera/{camera_id}"
    pubsub.publish(topic_str, json.dumps(msg_no_metadata))
    log.info(f"Published message to topic: {topic_str}")
    log.info(f"Message content (first 500 chars): {json.dumps(msg_no_metadata)[:500]}")

    # Wait for controller to process
    time.sleep(1)

    # Verify NO reid data stored in VDMS (scenario has no metadata)
    reid_count = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    assert reid_count == 0, f"Scenario 1: Expected 0 reid vectors, found {reid_count}"
    log.info("✓ Scenario 1 VDMS verification passed: No reid vectors stored")

    log.info("✓ Scenario 1 passed: No metadata flow validated")

    # =========================================================================
    # SCENARIO 2: Reid only metadata
    # =========================================================================
    log.info("=" * 80)
    log.info("SCENARIO 2: Testing with REID ONLY metadata")
    log.info("=" * 80)

    # Use pixel coordinates: two bounding boxes with sufficient area for reid extraction
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
      assert "metadata" in det, f"Scenario 2, detection {idx}: Missing metadata"
      assert "reid" in det["metadata"], f"Scenario 2, detection {idx}: Missing reid"
      assert "age" not in det["metadata"], f"Scenario 2, detection {idx}: Should not have semantic metadata"

      reid = det["metadata"]["reid"]
      assert "embedding_vector" in reid, f"Scenario 2, detection {idx}: Missing embedding_vector"
      assert "model_name" in reid, f"Scenario 2, detection {idx}: Missing model_name"
      assert isinstance(reid["embedding_vector"], str), \
             f"Scenario 2, detection {idx}: embedding should be base64 string"
      # Base64-encoded 256 float32s = 256*4 bytes = 1024 bytes -> ~1366 base64 chars
      assert len(reid["embedding_vector"]) > 1000, \
             f"Scenario 2, detection {idx}: embedding base64 string seems too short"

    log.info(f"✓ Scenario 2 message structure verified ({len(detections_reid_only)} detections with reid)")

    # Publish multiple frames to establish tracking
    # Tracker requires multiple observations before treating objects as tracked
    # Tracker config: effective_object_update_rate=10 FPS, max_unreliable_time_s=1.0
    num_frames = 25
    frame_interval = 0.1  # 10 FPS to match tracker config

    log.info(f"Publishing {num_frames} frames with reid metadata for tracking establishment...")
    for frame_num in range(num_frames):
      # Create fresh message with updated timestamp for each frame
      msg_reid_only = create_detection_message(camera_id, detections_reid_only)
      pubsub.publish(topic_str, json.dumps(msg_reid_only))
      time.sleep(frame_interval)

    log.info(f"Published {num_frames} reid-only frames to topic: {topic_str}")
    log.info(f"Reid message sample (first 800 chars): {json.dumps(msg_reid_only)[:800]}")

    # Wait for controller to process, establish tracking, extract reid, and store in VDMS
    # Pipeline: MQTT → Controller → Tracker (establishes track) → UUID Manager (collects reid)
    #         → UUID Manager runs similarity query (needs 12+ features)
    #         → Query completes, creates features_for_database entry
    #         → Stop publishing → Wait for tracks to timeout (max_unreliable_time=1.0s)
    #         → Send trigger message → Tracker prunes inactive tracks
    #         → UUID Manager stores reid to VDMS


    # IMPORTANT: Tracker uses FRAME COUNT not time for reliability
    # non_measurement_frames_dynamic = ceil(10 FPS * 0.8s) = 8 frames
    # We need to send 8+ empty frames to exceed this threshold

    log.info("Waiting for similarity query to complete...")
    time.sleep(2)  # Wait for similarity query to finish

    # Publish multiple empty frames to trigger track pruning
    # Tracker needs 8+ frames without measurement (non_measurement_frames_dynamic)
    log.info("Sending 10 empty frames to trigger track pruning...")
    for i in range(10):
      empty_msg = {
        "id": camera_id,
        "timestamp": get_iso_time(),
        "rate": 10.0,
        "objects": {"person": []}  # Empty person array - no new detections
      }
      pubsub.publish(topic_str, json.dumps(empty_msg))
      time.sleep(0.1)  # 10 FPS interval

    # Wait for 5+ seconds timeout to trigger stale feature flush
    # Plus additional time for background thread pool to complete VDMS insertion
    log.info("Waiting for stale feature timeout (5s) and VDMS storage (3s)...")
    time.sleep(8)  # 5s timeout + 3s for VDMS insertion to complete

    # Verify reid vectors stored in VDMS (should be 2 from this scenario)
    # Note: This cumulative (includes previous scenario), so check >= 2
    reid_count = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    assert reid_count >= 2, f"Scenario 2: Expected >= 2 reid vectors, found {reid_count}"
    log.info(f"✓ Scenario 2 VDMS verification passed: {reid_count} reid vectors stored")

    log.info("✓ Scenario 2 passed: Reid-only flow validated")

    # =========================================================================
    # SCENARIO 3: Semantic only metadata
    # =========================================================================
    log.info("=" * 80)
    log.info("SCENARIO 3: Testing with SEMANTIC ONLY metadata")
    log.info("=" * 80)

    # Use pixel coordinates for semantic-only detection
    detections_semantic_only = [
      ({"x": 100, "y": 100, "width": 100, "height": 200},
       None,
       semantic_attrs.copy())
    ]

    msg_semantic_only = create_detection_message(camera_id, detections_semantic_only)

    # Verify structure
    det = msg_semantic_only["objects"]["person"][0]
    assert "metadata" in det, "Scenario 3: Missing metadata"
    assert "reid" not in det["metadata"], "Scenario 3: Should not have reid"
    assert "age" in det["metadata"], "Scenario 3: Missing age"
    assert "gender" in det["metadata"], "Scenario 3: Missing gender"
    assert det["metadata"]["age"]["value"] == 28, "Scenario 3: Age value incorrect"
    assert det["metadata"]["gender"]["value"] == "male", "Scenario 3: Gender value incorrect"

    log.info("✓ Scenario 3 message structure verified (semantic attributes: age, gender)")

    # Publish message to MQTT broker for controller to process
    pubsub.publish(topic_str, json.dumps(msg_semantic_only))
    log.info(f"Published semantic-only message to topic: {topic_str}")

    # Wait for controller to process
    time.sleep(2)

    # Verify NO additional reid vectors stored (semantic only, no reid)
    # Count should be same as after Scenario 2
    reid_count_after_semantic = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    assert reid_count_after_semantic >= 2, f"Scenario 3: Reid count should remain >= 2, found {reid_count_after_semantic}"
    log.info(f"✓ Scenario 3 VDMS verification passed: No new reid vectors (still {reid_count_after_semantic})")

    log.info("✓ Scenario 3 passed: Semantic-only flow validated")

    # =========================================================================
    # SCENARIO 4: Reid + Semantic metadata
    # =========================================================================
    log.info("=" * 80)
    log.info("SCENARIO 4: Testing with REID + SEMANTIC metadata")
    log.info("=" * 80)

    # Use pixel coordinates for combined reid+semantic detections
    detections_combined = [
      ({"x": 100, "y": 100, "width": 100, "height": 200},
       (embeddings[2], "person-reidentification-retail-0287"),
       semantic_attrs.copy()),
      ({"x": 500, "y": 100, "width": 100, "height": 200},
       (embeddings[3], "person-reidentification-retail-0287"),
       {"age": {"value": 35, "confidence": 0.78}, "gender": {"value": "female", "confidence": 0.88}})
    ]

    msg_combined = create_detection_message(camera_id, detections_combined)

    # Verify structure for both detections
    for idx, det in enumerate(msg_combined["objects"]["person"]):
      assert "metadata" in det, f"Scenario 4, detection {idx}: Missing metadata"
      assert "reid" in det["metadata"], f"Scenario 4, detection {idx}: Missing reid"
      assert "age" in det["metadata"], f"Scenario 4, detection {idx}: Missing age"
      assert "gender" in det["metadata"], f"Scenario 4, detection {idx}: Missing gender"

      # Verify reid structure
      reid = det["metadata"]["reid"]
      assert "embedding_vector" in reid, f"Scenario 4, detection {idx}: Missing embedding_vector"
      assert "model_name" in reid, f"Scenario 4, detection {idx}: Missing model_name"
      assert isinstance(reid["embedding_vector"], str), \
             f"Scenario 4, detection {idx}: embedding should be base64 string"
      assert len(reid["embedding_vector"]) > 1000, \
             f"Scenario 4, detection {idx}: embedding base64 string seems too short"

      # Verify semantic structure
      assert "value" in det["metadata"]["age"], f"Scenario 4, detection {idx}: age missing value"
      assert "confidence" in det["metadata"]["age"], f"Scenario 4, detection {idx}: age missing confidence"

    log.info(f"✓ Scenario 4 message structure verified ({len(detections_combined)} detections with reid+semantic)")

    # Publish multiple frames to establish tracking
    # Same approach as Scenario 2: multiple frames for tracker to establish tracks
    num_frames = 25
    frame_interval = 0.1  # 10 FPS

    log.info(f"Publishing {num_frames} frames with reid+semantic metadata...")
    for frame_num in range(num_frames):
      # Create fresh message with updated timestamp for each frame
      msg_combined = create_detection_message(camera_id, detections_combined)
      pubsub.publish(topic_str, json.dumps(msg_combined))
      time.sleep(frame_interval)

    log.info(f"Published {num_frames} combined reid+semantic frames to topic: {topic_str}")

    # Wait for controller to process and store in VDMS
    # Same pipeline as Scenario 2: wait for query + send empty frames + wait for timeout flush
    log.info("Waiting for similarity query to complete...")
    time.sleep(2)  # Wait for similarity query to finish

    log.info("Sending 10 empty frames to trigger track pruning...")
    for i in range(10):
      empty_msg = {
        "id": camera_id,
        "timestamp": get_iso_time(),
        "rate": 10.0,
        "objects": {"person": []}
      }
      pubsub.publish(topic_str, json.dumps(empty_msg))
      time.sleep(0.1)  # 10 FPS interval

    log.info("Waiting for stale feature timeout (5s) and VDMS storage (3s)...")
    time.sleep(8)  # 5s timeout + 3s for VDMS insertion

    # Verify reid vectors stored (should have 2 more from this scenario)
    final_reid_count = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    assert final_reid_count >= 4, f"Scenario 4: Expected >= 4 reid vectors total, found {final_reid_count}"
    log.info(f"✓ Scenario 4 VDMS verification passed: {final_reid_count} total reid vectors stored")

    log.info("✓ Scenario 4 passed: Combined reid+semantic flow validated")

    # =========================================================================
    # Final validation and summary
    # =========================================================================
    log.info("=" * 80)
    log.info("FINAL VALIDATION AND SUMMARY")
    log.info("=" * 80)

    # Wait a bit more for any delayed messages
    time.sleep(2)

    # Verify scene output messages were received
    log.info(f"Total scene output messages received: {len(received_scene_messages)}")
    assert len(received_scene_messages) >= 4, \
           f"Expected at least 4 scene messages (one per scenario), got {len(received_scene_messages)}"

    # Verify final VDMS state
    final_reid_total = query_vdms_reid_count(camera_id, scene_uid, use_tls=False)
    log.info(f"Final VDMS reid vector count: {final_reid_total}")
    assert final_reid_total >= 4, \
           f"Expected at least 4 reid vectors total, found {final_reid_total}"

    # Summary
    log.info("=" * 80)
    log.info("TEST SUMMARY")
    log.info("=" * 80)
    log.info(f"✓ Scenario 1 (No metadata): Verified NO reid stored")
    log.info(f"✓ Scenario 2 (Reid only): Verified reid vectors stored")
    log.info(f"✓ Scenario 3 (Semantic only): Verified NO new reid vectors")
    log.info(f"✓ Scenario 4 (Reid + Semantic): Verified reid vectors with semantic metadata")
    log.info(f"✓ Scene output messages: {len(received_scene_messages)} received")
    log.info(f"✓ VDMS storage: {final_reid_total} total reid vectors")
    log.info("=" * 80)
    log.info("ALL INTEGRATION TESTS PASSED")
    log.info("=" * 80)

    # Cleanup
    pubsub.loopStop()
    pubsub.disconnect()

    # =========================================================================
    # Additional validation tests (format compatibility)
    # =========================================================================
    log.info("=" * 80)
    log.info("ADDITIONAL VALIDATION TESTS (Format Compatibility)")
    log.info("=" * 80)

    # Test: Base64 encoding/decoding (legacy format support)
    log.info("Testing base64 encoding/decoding...")
    test_embedding = embeddings[0]
    encoded = encode_reid_base64(test_embedding)
    decoded_bytes = base64.b64decode(encoded)
    decoded_array = np.array(struct.unpack("256f", decoded_bytes))

    assert np.allclose(test_embedding, decoded_array, rtol=1e-5), \
           "Base64 encode/decode mismatch"

    log.info("✓ Base64 encoding/decoding verified")

    # Test: Format compatibility (new dict format vs legacy base64)
    log.info("Testing format compatibility...")
    new_format = {
      "embedding_vector": embeddings[0].tolist(),
      "model_name": "person-reidentification-retail-0287"
    }
    legacy_format = encode_reid_base64(embeddings[0])

    assert isinstance(new_format, dict), "New format should be dict"
    assert isinstance(legacy_format, str), "Legacy format should be string"
    assert "embedding_vector" in new_format, "New format missing embedding_vector key"
    assert "model_name" in new_format, "New format missing model_name key"

    log.info("✓ Format compatibility verified")

    # Test: Numpy array conversions
    log.info("Testing numpy array conversions...")
    numpy_array = np.array(embeddings[0])
    as_list = numpy_array.tolist()
    back_to_numpy = np.array(as_list)

    assert isinstance(as_list, list), "Converted value should be list"
    assert len(as_list) == 256, "List should have 256 elements"
    assert np.allclose(numpy_array, back_to_numpy), "Round-trip conversion should preserve values"

    log.info("✓ Numpy array conversions validated")

    # Test: Embedding similarity calculations
    log.info("Testing embedding similarity calculations...")
    emb1 = embeddings[0] / np.linalg.norm(embeddings[0])
    emb2 = embeddings[0] / np.linalg.norm(embeddings[0])
    similarity_same = np.dot(emb1, emb2)

    assert similarity_same > 0.99, f"Same embedding similarity should be ~1.0, got {similarity_same}"

    emb3 = embeddings[1] / np.linalg.norm(embeddings[1])
    similarity_diff = np.dot(emb1, emb3)

    assert similarity_diff < similarity_same, \
           f"Different embeddings should have lower similarity: {similarity_diff} vs {similarity_same}"

    log.info(f"✓ Embedding similarity verified (same={similarity_same:.4f}, diff={similarity_diff:.4f})")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    log.info("=" * 80)
    log.info("TEST SUMMARY")
    log.info("=" * 80)
    log.info("✓ Scenario 1: No metadata - PASSED")
    log.info("✓ Scenario 2: Reid only - PASSED")
    log.info("✓ Scenario 3: Semantic only - PASSED")
    log.info("✓ Scenario 4: Reid + Semantic - PASSED")
    log.info("✓ Base64 encoding/decoding - PASSED")
    log.info("✓ Format compatibility - PASSED")
    log.info("✓ Numpy array conversions - PASSED")
    log.info("✓ Embedding similarity calculations - PASSED")
    log.info("=" * 80)
    log.info("ALL TESTS PASSED")
    log.info("=" * 80)

    exit_code = 0

  except Exception as e:
    log.error(f"Test failed with exception: {e}")
    import traceback
    traceback.print_exc()
    raise

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0, "Reid data flow test failed"
