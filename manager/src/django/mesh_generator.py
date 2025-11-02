# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from io import BytesIO
import json
import time
import base64
import requests
import os
import threading
from typing import Dict
import numpy as np
from scipy.spatial.transform import Rotation

from django.core.files.base import ContentFile
import paho.mqtt.client as mqtt
import trimesh

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from scene_common.mesh_util import mergeMesh
from scene_common.options import QUATERNION
from scene_common import log

class CameraImageCollector:
  """Collects calibration images from all cameras in a scene."""

  def __init__(self):
    self.collected_images = {}
    self.image_condition = threading.Condition()
    self.max_wait_time = 30  # seconds

  def collectImagesForScene(self, scene, mqtt_client):
    """
    Collect calibration images from all cameras attached to the scene.

    Args:
      scene: Scene object containing cameras
      mqtt_client: MQTT client for communication

    Returns:
      dict: Dictionary mapping camera_id to base64 image data
    """
    # Get all cameras for this scene
    cameras = scene.sensor_set.filter(type='camera')

    if not cameras.exists():
      raise ValueError("No cameras found in scene")

    log.info(f"Found {cameras.count()} cameras in scene {scene.name}")

    # Reset collected images
    self.collected_images = {}

    # Subscribe to image calibration topics for all cameras
    for camera in cameras:
      topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera.sensor_id)
      mqtt_client.addCallback(topic, self._onCalibrationImageReceived)
      log.info(f"Subscribed to calibration images for camera {camera.sensor_id}")

    # Send getcalibrationimage command to all cameras
    for camera in cameras:
      cmd_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera.sensor_id)
      msg = mqtt_client.publish(cmd_topic, "getcalibrationimage", qos=2)
      log.info(f"Sent getcalibrationimage command to camera {camera.sensor_id}")
      if not msg.is_published() and msg.rc == mqtt.MQTT_ERR_SUCCESS:
        mqtt_client.loopStart()
        msg.wait_for_publish()
        mqtt_client.loopStop()

    # Wait for images to be collected
    self.image_condition.acquire()
    try:
      start_time = time.time()
      while len(self.collected_images) < cameras.count():
        elapsed = time.time() - start_time
        remaining_time = self.max_wait_time - elapsed

        if remaining_time <= 0:
          break

        self.image_condition.wait(timeout=remaining_time)

    finally:
      self.image_condition.release()

    # Unsubscribe from topics
    for camera in cameras:
      topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera.sensor_id)
      mqtt_client.removeCallback(topic)

    if len(self.collected_images) < cameras.count():
      missing_cameras = [cam.sensor_id for cam in cameras if cam.sensor_id not in self.collected_images]
      raise ValueError(f"Failed to collect images from cameras: {missing_cameras}")

    log.info(f"Successfully collected images from {len(self.collected_images)} cameras")
    return self.collected_images

  def _onCalibrationImageReceived(self, client, userdata, message):
    """MQTT callback for receiving calibration images."""
    try:
      msg_data = json.loads(message.payload.decode("utf-8"))
      topic = PubSub.parseTopic(message.topic)
      camera_id = topic['camera_id']

      if 'image' in msg_data:
        self.image_condition.acquire()
        try:
          self.collected_images[camera_id] = {
            'data': msg_data['image'],
            'timestamp': msg_data.get('timestamp', ''),
            'filename': f"{camera_id}_calibration.jpg"
          }
          log.info(f"Received calibration image from camera {camera_id}")
          self.image_condition.notify()
        finally:
          self.image_condition.release()
      else:
        log.warning(f"No image data in calibration message from camera {camera_id}")

    except Exception as e:
      log.error(f"Error processing calibration image: {e}")


class MappingServiceClient:
  """Client for interacting with the mapping service API."""

  def __init__(self):
    # Get mapping service URL from environment or use default
    self.base_url = os.environ.get('MAPPING_SERVICE_URL', 'https://mapping.scenescape.intel.com:8444')
    self.timeout = 300  # 5 minutes timeout for mesh generation
    self.health_timeout = 5  # Short timeout for health checks

    # Obtain rootcert for HTTPS requests, same logic as models.py
    self.rootcert = os.environ.get("BROKERROOTCERT")
    if self.rootcert is None:
      self.rootcert = "/run/secrets/certs/scenescape-ca.pem"

  def reconstructMesh(self, images: Dict[str, Dict], mesh_type='mesh'):
    """
    Call mapping service to reconstruct 3D mesh from images.

    Args:
      images: Dictionary of camera images with base64 data
      mesh_type: Output type ('mesh' or 'pointcloud')

    Returns:
      dict: Response from mapping service
    """
    # Prepare request data
    image_list = []
    for camera_id, image_data in images.items():
      image_list.append({
        'data': image_data['data'],
        'filename': image_data['filename']
      })

    request_data = {
      'output_format': 'glb',
      'mesh_type': mesh_type,
      'images': image_list
    }

    log.info(f"Sending {len(image_list)} images to mapping service for reconstruction")

    try:
      response = requests.post(
        f"{self.base_url}/reconstruction",
        json=request_data,
        timeout=self.timeout,
        headers={'Content-Type': 'application/json'},
        verify=self.rootcert
      )

      if response.status_code == 200:
        result = response.json()
        log.info(f"Mapping service completed successfully in {result.get('processing_time', 0):.2f}s")
        return result
      else:
        error_data = response.json() if response.content else {}
        error_msg = error_data.get('error', f'HTTP {response.status_code}')
        log.error(f"Mapping service error: {error_msg}")
        raise Exception(f"Mapping service error: {error_msg}")

    except requests.exceptions.Timeout:
      raise Exception("Mapping service request timed out")
    except requests.exceptions.ConnectionError:
      raise Exception("Could not connect to mapping service")
    except Exception as e:
      log.error(f"Mapping service request failed: {e}")
      raise

  def checkHealth(self):
    """
    Check if the mapping service is available and healthy.

    Returns:
      dict: Health status with 'available' boolean and optional 'models' info
    """
    try:
      response = requests.get(
        f"{self.base_url}/health",
        timeout=self.health_timeout,
        headers={'Content-Type': 'application/json'},
        verify=self.rootcert
      )

      if response.status_code == 200:
        health_data = response.json()
        return {
          'available': True,
          'status': health_data.get('status', 'unknown'),
          'models': health_data.get('models', {})
        }
      else:
        return {
          'available': False,
          'error': f'HTTP {response.status_code}'
        }

    except requests.exceptions.Timeout:
      return {
        'available': False,
        'error': 'Health check timed out'
      }
    except requests.exceptions.ConnectionError:
      return {
        'available': False,
        'error': 'Could not connect to mapping service'
      }
    except Exception as e:
      return {
        'available': False,
        'error': str(e)
      }


class MeshGenerator:
  """Main class for generating 3D meshes from scene cameras."""

  def __init__(self):
    self.image_collector = CameraImageCollector()
    self.mapping_client = MappingServiceClient()

  def generateMeshFromScene(self, scene, mesh_type='mesh'):
    """
    Generate a 3D mesh from all cameras in a scene.

    Args:
      scene: Scene object
      mesh_type: Type of mesh output

    Returns:
      dict: Result with success status and details
    """
    start_time = time.time()

    # Initialize MQTT client for camera communication
    broker = os.environ.get("BROKER")
    auth = os.environ.get("BROKERAUTH")
    rootcert = os.environ.get("BROKERROOTCERT")
    if rootcert is None:
      rootcert = "/run/secrets/certs/scenescape-ca.pem"
    cert = os.environ.get("BROKERCERT")
    try:
      log.info(f"Connecting to MQTT broker at {broker}")
      mqtt_client = PubSub(auth, cert, rootcert, broker)
      mqtt_client.connect()

      # Collect images from all cameras in the scene
      log.info(f"Starting mesh generation for scene {scene.name}")
      images = self.image_collector.collectImagesForScene(scene, mqtt_client)

      # Get scene cameras (in same order as images)
      cameras = scene.sensor_set.filter(type='camera').order_by('id')

      log.info(f"Collected {len(images)} images, calling mapping service")
      # Call mapping service to generate mesh
      mapping_result = self.mapping_client.reconstructMesh(
        images, mesh_type
      )

      log.info("Mapping service returned result")

      # Update scene cameras with poses and intrinsics from mapping service
      if mapping_result.get('success'):
        self._updateSceneCamerasWithMappingResult(mapping_result, cameras)

      # Save the generated mesh to the scene
      if mapping_result.get('success') and mapping_result.get('glb_data'):
        self._saveMeshToScene(scene, mapping_result['glb_data'])

        processing_time = time.time() - start_time
        log.info(f"Mesh generation completed successfully in {processing_time:.2f}s")

        return {
          'success': True,
          'message': f'Successfully generated mesh from {len(images)} cameras',
          'processing_time': processing_time,
          'camera_count': len(images)
        }
      else:
        raise Exception("Mapping service did not return GLB data")

    except Exception as e:
      processing_time = time.time() - start_time
      log.error(f"Mesh generation failed: {e}")
      return {
        'success': False,
        'error': str(e),
        'processing_time': processing_time
      }
    finally:
      # Cleanup MQTT connection
      try:
        mqtt_client.disconnect()
      except:
        pass

  def _updateSceneCamerasWithMappingResult(self, mapping_result, cameras):
    """
    Update scene cameras with poses and intrinsics returned by mapping service.

    Args:
      scene: Scene object containing cameras
      mapping_result: Result from mapping service containing camera_poses and intrinsics
      cameras: QuerySet of camera objects in enumeration order
    """
    try:
      camera_poses = mapping_result.get('camera_poses', [])
      intrinsics_list = mapping_result.get('intrinsics', [])

      if not camera_poses or not intrinsics_list:
        log.warning("Mapping service did not return camera poses or intrinsics")
        return

      if len(camera_poses) != len(intrinsics_list):
        log.error(f"Mismatch in mapping service results: {len(camera_poses)} poses vs {len(intrinsics_list)} intrinsics")
        return

      cameras_list = list(cameras)
      if len(cameras_list) != len(camera_poses):
        log.error(f"Camera count mismatch: {len(cameras_list)} scene cameras vs {len(camera_poses)} mapping results")
        return

      log.info(f"Updating {len(cameras_list)} cameras with mapping service results")

      # Update each camera with corresponding pose and intrinsics
      for i, camera in enumerate(cameras_list):
        try:
          pose_data = camera_poses[i]
          intrinsics_matrix = intrinsics_list[i]

          # Convert mapping service format to Django camera format
          self._updateCameraParameters(camera, pose_data, intrinsics_matrix)

          log.info(f"Updated camera {camera.sensor_id} with new pose and intrinsics")

        except Exception as e:
          log.error(f"Failed to update camera {camera.sensor_id}: {e}")

    except Exception as e:
      log.error(f"Failed to update scene cameras: {e}")

  def _updateCameraParameters(self, camera, pose_data, intrinsics_matrix):
    """
    Update a single camera with new pose and intrinsics.

    Args:
      camera: Camera model instance
      pose_data: Dictionary with 'rotation' (quaternion) and 'translation' from mapping service
      intrinsics_matrix: 3x3 intrinsics matrix from mapping service
    """
    try:
      # Extract pose data
      rotation_quat = pose_data['rotation']  # [w, x, y, z]
      translation = pose_data['translation']  # [x, y, z]

      # Transform from OpenCV coordinates (API output) to SceneScape Z-up coordinates
      rotation_quat_scenescape, translation_scenescape = self._transformOpenCVToSceneScapeCoordinates(
        rotation_quat, translation
      )

      # Extract intrinsics (3x3 matrix -> fx, fy, cx, cy)
      intrinsics_array = np.array(intrinsics_matrix)
      fx = intrinsics_array[0, 0]
      fy = intrinsics_array[1, 1]
      cx = intrinsics_array[0, 2]
      cy = intrinsics_array[1, 2]

      # Update camera model fields
      camera.cam.intrinsics_fx = fx
      camera.cam.intrinsics_fy = fy
      camera.cam.intrinsics_cx = cx
      camera.cam.intrinsics_cy = cy

      # Update camera transform using QUATERNION format
      # Django QUATERNION format expects: [translation_x, translation_y, translation_z,
      #                   rotation_x, rotation_y, rotation_z, rotation_w,
      #                   scale_x, scale_y, scale_z]
      # Use transformed coordinates and reorder quaternion from [w, x, y, z] to [x, y, z, w]
      camera.cam.transforms = [
        translation_scenescape[0], translation_scenescape[1], translation_scenescape[2],  # translation
        rotation_quat_scenescape[1], rotation_quat_scenescape[2], rotation_quat_scenescape[3], rotation_quat_scenescape[0],  # quaternion [x, y, z, w]
        1.0, 1.0, 1.0  # scale (default to 1.0)
      ]
      camera.cam.transform_type = QUATERNION  # Use quaternion transform type

      # Save the camera
      camera.cam.save()

    except Exception as e:
      log.error(f"Error updating camera {camera.sensor_id}: {e}")
      raise

  def _saveMeshToScene(self, scene, glb_data_base64):
    """
    Save the generated GLB mesh to the scene's map field.

    Args:
      scene: Scene object to update
      glb_data_base64: Base64 encoded GLB file data
    """
    try:
      # Decode base64 GLB data
      glb_bytes = base64.b64decode(glb_data_base64)
      # Directly use the decoded bytes without re-exporting unless merging is needed
      mesh = trimesh.load(BytesIO(glb_bytes), file_type='glb')
      merged_mesh = mergeMesh(mesh)

      filename = f"{scene.name}_generated_mesh.glb"
      # Only export if mesh was merged/modified, else use original bytes
      if merged_mesh is not mesh:
        glb_exported_bytes = merged_mesh.export(file_type='glb')
      else:
        glb_exported_bytes = glb_bytes

      log.info(f"Saving generated mesh to scene {scene.name} as {filename}")
      # Save to scene's map field using the file-like object
      scene.map.save(filename, ContentFile(glb_exported_bytes), save=True)

      # Update the map_processed timestamp
      scene.map_processed = get_iso_time()
      scene.save(update_fields=['map_processed'])

      log.info(f"Saved generated mesh to scene {scene.name} as {filename}")

    except Exception as e:
      log.error(f"Failed to save mesh to scene: {e}")
      raise Exception(f"Failed to save mesh file: {e}")

  def _transformOpenCVToSceneScapeCoordinates(self, rotation_quat, translation):
    """
    Transform camera pose from OpenCV coordinate system to SceneScape Z-up coordinate system.

    OpenCV coordinates (API output):
    - X: right, Y: down, Z: forward (into scene)

    SceneScape Z-up coordinates:
    - X: right, Y: forward, Z: up (world coordinates)

    Args:
      rotation_quat: Quaternion [w, x, y, z] in OpenCV coordinates
      translation: Translation [x, y, z] in OpenCV coordinates

    Returns:
      tuple: (transformed_quaternion, transformed_translation) for SceneScape coordinates
    """
    # Create coordinate transformation matrix: OpenCV -> SceneScape Z-up
    # OpenCV (X:right, Y:down, Z:forward) -> SceneScape (X:right, Y:forward, Z:up)
    coord_transform = np.array([
      [1,  0,  0],   # X stays the same (right)
      [0,  0,  1],   # Y becomes old Z (forward)
      [0, -1,  0]  # Z becomes old -Y (up)
    ])

    # Transform translation
    translation_np = np.array(translation)
    translation_scenescape = coord_transform @ translation_np

    # Transform rotation quaternion
    # Convert quaternion to rotation matrix, transform, then back to quaternion

    # Convert [w, x, y, z] to scipy format [x, y, z, w]
    quat_scipy = [rotation_quat[1], rotation_quat[2], rotation_quat[3], rotation_quat[0]]
    rotation_matrix = Rotation.from_quat(quat_scipy).as_matrix()

    # Apply coordinate transformation: R' = T * R * T^-1
    rotation_matrix_scenescape = coord_transform @ rotation_matrix @ coord_transform.T

    # Convert back to quaternion in [w, x, y, z] format
    quat_scenescape_scipy = Rotation.from_matrix(rotation_matrix_scenescape).as_quat()
    rotation_quat_scenescape = [quat_scenescape_scipy[3], quat_scenescape_scipy[0],
                   quat_scenescape_scipy[1], quat_scenescape_scipy[2]]

    return rotation_quat_scenescape, translation_scenescape.tolist()
