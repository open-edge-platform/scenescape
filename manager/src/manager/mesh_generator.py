# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from io import BytesIO
from contextlib import ExitStack
import json
import time
import base64
import requests
import os
import threading
from typing import Dict, List
import tempfile
import subprocess
from pathlib import Path
import mimetypes

import numpy as np
from scipy.spatial.transform import Rotation
from django.core.files.base import ContentFile
import paho.mqtt.client as mqtt
import trimesh

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from scene_common.mesh_util import mergeMesh, checkMeshConnectivity
from scene_common import log
from manager.serializers import CamSerializer

ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "video/x-msvideo",
}

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

class CameraImageCollector:
  """Collects calibration images from all cameras in a scene."""

  def __init__(self):
    self.collected_images = {}
    self.image_condition = threading.Condition()
    self.max_wait_time_per_cam = 5  # seconds

  def collectImagesForScene(self, cameras, mqtt_client):
    """
    Collect calibration images from all cameras attached to the scene.

    Args:
      scene: Scene object containing cameras
      mqtt_client: MQTT client for communication

    Returns:
      dict: Dictionary mapping camera_id to base64 image data
    """

    if not cameras.exists():
      log.warning("No cameras found for scene when attempting to collect calibration images; returning empty list")
      return []

    # Reset collected images
    self.collected_images = {}

    # Subscribe to image calibration topics for all cameras
    for camera in cameras:
      topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera.sensor_id)
      mqtt_client.addCallback(topic, self._onCalibrationImageReceived, qos=2)
      log.info(f"Subscribed to calibration images for camera {camera.sensor_id}")

    # Start MQTT loop to process incoming messages
    mqtt_client.loopStart()

    try:
      # Send getcalibrationimage command to all cameras
      for camera in cameras:
        cmd_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera.sensor_id)
        msg = mqtt_client.publish(cmd_topic, "getcalibrationimage", qos=2)
        log.info(f"Sent getcalibrationimage command to camera {camera.sensor_id}")
        msg.wait_for_publish()

      # Wait for images to be collected
      self.image_condition.acquire()
      try:
        start_time = time.time()
        while len(self.collected_images) < cameras.count():
          elapsed = time.time() - start_time
          remaining_time = (self.max_wait_time_per_cam * cameras.count()) - elapsed

          if remaining_time <= 0:
            break

          self.image_condition.wait(timeout=remaining_time)

      finally:
        self.image_condition.release()

    finally:
      # Stop MQTT loop
      mqtt_client.loopStop()

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
    self.base_url = os.environ.get('MAPPING_SERVICE_URL', 'https://mapping.scenescape.intel.com:8444/v1')
    self.timeout_per_camera = 30  # timeout (in seconds) per camera for mesh generation
    self.health_timeout = 5  # Short timeout for health checks

    # Obtain rootcert for HTTPS requests, same logic as models.py
    self.rootcert = os.environ.get("BROKERROOTCERT")
    if self.rootcert is None:
      self.rootcert = "/run/secrets/certs/scenescape-ca.pem"

  def startReconstructMesh(
    self,
    images: Dict[str, Dict],
    camera_order: List[str],
    camera_location_order: List,
    mesh_type: str = "mesh",
    uploaded_map=None,
  ):
    """
    Call mapping service to reconstruct 3D mesh from images.

    Args:
      images: Dictionary of camera images with base64 data
      camera_order: List of camera IDs in the order cameras should be processed
      mesh_type: Output type ('mesh' or 'pointcloud')

    Returns:
      dict: Response from mapping service
    """

    # Form data parameters
    data = {
        "output_format": "glb",
        "mesh_type": mesh_type,
    }

    camera_loc_by_id = {
      cam_id: cam_loc
      for cam_id, cam_loc in zip(camera_order, camera_location_order)
    }
    log.info(f"Sending {len(images)} images to mapping service for reconstruction")

    files = []

    try:
      # ExitStack lets us use context managers for an arbitrary number of files
      # and guarantees they remain open until after requests.post completes.
      with ExitStack() as stack:
        # Iterate in the specified camera order
        for camera_id in camera_order:
          if camera_id in images:
            img_bytes = base64.b64decode(images[camera_id]["data"])
            files.append(
                (
                    "images",
                    (
                        images[camera_id]["filename"],
                        BytesIO(img_bytes),
                        "image/jpeg",
                    ),
                )
            )
            files.append(("camera_ids", (None, camera_id)))
            cam_loc = camera_loc_by_id.get(camera_id)
            if cam_loc is not None:
              cam_loc_clean = {
                "translation": list(cam_loc["translation"]),
                "rotation": list(cam_loc["rotation"]),
                "scale": list(cam_loc.get("scale", [1.0, 1.0, 1.0])),
              }
              files.append(("camera_locations", (None, json.dumps(cam_loc_clean))))
            else:
              log.warning(f"No camera location for {camera_id}")
          else:
            log.warning(
                f"Camera {camera_id} in camera_order but not in images dict"
            )

        if uploaded_map:
          p = Path(uploaded_map)
          if not p.exists():
            raise FileNotFoundError(f"Video not found: {uploaded_map}")
          if not p.is_file():
            raise FileNotFoundError(f"Video path is not a file: {uploaded_map}")

          mime_type, _ = mimetypes.guess_type(p.name)
          mime_type = mime_type or "application/octet-stream"

          # Keep file handle open for the duration of the request
          f = stack.enter_context(p.open("rb"))
          files.append(("video", (p.name, f, mime_type)))

        response = requests.post(
          f"{self.base_url}/reconstruction",
          data=data,
          files=files,
          timeout=int(os.getenv("GUNICORN_TIMEOUT", "300")),
          verify=self.rootcert,
        )
      # After we exit the `with ExitStack()` block, all file handles are closed.

      if response.status_code == 200:
        result = response.json()
        log.info(
            f"Mapping service completed successfully in {result.get('processing_time', 0):.2f}s"
        )
        return result

      error_data = response.json() if response.content else {}
      error_msg = error_data.get("error", f"HTTP {response.status_code}")
      log.error(f"Mapping service error: {error_msg}")
      raise Exception(f"Mapping service error: {error_msg}")

    except requests.exceptions.Timeout:
      raise Exception("Mapping service request timed out")
    except requests.exceptions.ConnectionError:
      raise Exception("Could not connect to mapping service")
    except Exception as e:
      log.error(f"Mapping service request failed: {e}")
      raise

  def getReconstructionStatus(self, request_id: str):
    url = f"{self.base_url}/reconstruction/status/{request_id}"
    r = requests.get(url, timeout=self.health_timeout, verify=self.rootcert)
    try:
      payload = r.json()
    except Exception:
      payload = {"success": False, "error": "Non-JSON response from mapping service", "raw": r.text}

    payload.setdefault("success", r.ok)
    payload["status_code"] = r.status_code
    return payload

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

      if response.status_code in (200, 202):
        health_data = response.json()
        details = health_data.get('details', {})
        models = details.get('models', {})
        if not models and 'model_loaded' in health_data:
          models = {
            'loaded': health_data.get('model_loaded', False),
            'active': health_data.get('model', 'unknown'),
          }

        return {
          'available': True,
          'status': health_data.get('status', 'unknown'),
          'ready': bool(health_data.get('ready', False)),
          'models': models,
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

  def isValidVideo(self, file_obj) -> bool:
    """
    Lightweight magic-header check for common video containers.
    Does NOT guarantee decodability, but blocks obvious non-videos.
    """
    try:
      file_obj.seek(0)
      header = file_obj.read(16)
      file_obj.seek(0)

      # MP4 / MOV: 'ftyp' box at offset 4
      if len(header) >= 12 and header[4:8] == b"ftyp":
        return True

      # MKV / WebM: EBML header
      if header.startswith(b"\x1A\x45\xDF\xA3"):
        return True

      # AVI: RIFF....AVI
      if header.startswith(b"RIFF") and b"AVI" in header:
        return True

      return False
    except Exception:
      return False

  def materializeUploadedVideo(self, uploaded_file):
    if not uploaded_file:
      return None, False

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()

    if content_type not in ALLOWED_VIDEO_MIME_TYPES:
      raise ValueError(f"Uploaded file must be a video. Got content-type: {content_type or 'unknown'}")

    if not self.isValidVideo(uploaded_file):
      raise ValueError("Uploaded file does not look like a valid video")

    filename = getattr(uploaded_file, "name", "") or ""
    suffix = Path(filename).suffix.lower()

    # The extension check must be an inline literal set (not a reference to
    # ALLOWED_VIDEO_EXTENSIONS) for CodeQL's path-injection analysis to treat
    # it as sanitizing suffix before it reaches NamedTemporaryFile below.
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
      raise ValueError(f"Unsupported video file extension: {suffix or 'none'}")

    try:
      path = uploaded_file.temporary_file_path()
      return path, False
    except Exception:
      with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        for chunk in uploaded_file.chunks():
          tmp.write(chunk)
        return tmp.name, True

  def _checkMeshConnectivity(self, glb_data_base64):
    """
    Decode/load/merge the reconstructed mesh once and validate connectivity.

    Returns:
      tuple: (error_message, merged_mesh). error_message is a string when the
        mesh is split into multiple dominant, spatially separate surfaces or
        cannot be decoded, otherwise None. merged_mesh is the loaded trimesh
        object to reuse downstream, or None when decode/load failed.
    """
    try:
      glb_bytes = base64.b64decode(glb_data_base64)
      mesh = trimesh.load(BytesIO(glb_bytes), file_type='glb')
      merged_mesh = mergeMesh(mesh)
    except Exception as e:
      # Decode/load errors will also break mesh saving; fail early before any scene mutation.
      log.error(f"Failed to decode/load reconstructed mesh: {e}")
      return "Mapping service returned invalid GLB data", None

    try:
      return checkMeshConnectivity(merged_mesh), merged_mesh
    except Exception as e:
      # Connectivity analysis failure should not block the reconstruction pipeline.
      log.warning(f"Could not analyze mesh connectivity: {e}")
      return None, merged_mesh

  def _is_camera_calibrated(self, camera, serializer):
    """
    Determine if a camera has a calibrated pose (not default/uncalibrated).

    A camera is considered calibrated if:
    - It has non-empty transforms stored
    - It has non-None translation and rotation from the serializer

    Args:
      camera: Cam object
      serializer: CamSerializer instance

    Returns:
      bool: True if camera is calibrated, False if uncalibrated
    """
    try:
      # An empty transforms list still serializes to a zeroed identity pose, so it
      # has to be rejected here or an uncalibrated camera looks calibrated.
      if not camera.cam.transforms:
        return False

      t = serializer.get_translation(camera)
      q = serializer.get_rotation(camera)
      return t is not None and q is not None
    except Exception as e:
      log.debug(f"Error checking calibration state for {camera.sensor_id}: {e}")
      return False

  def startMeshGeneration(self, scene, mesh_type='mesh', uploaded_map=None):
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
    suffix = (Path(getattr(uploaded_map, "name", "")).suffix or "").lower()
    if rootcert is None:
      rootcert = "/run/secrets/certs/scenescape-ca.pem"
    cert = os.environ.get("BROKERCERT")
    try:
      log.info(f"Connecting to MQTT broker at {broker}")
      mqtt_client = PubSub(auth, cert, rootcert, broker)
      mqtt_client.connect()

      cameras = scene.sensor_set.filter(type='camera').order_by('id')
      uploaded_map_path = None

      # Collect images from all cameras in the scene
      log.info(f"Starting mesh generation for scene {scene.name}")
      images = self.image_collector.collectImagesForScene(cameras, mqtt_client)

      if uploaded_map:
        if suffix not in ALLOWED_VIDEO_EXTENSIONS:
          return {
              "success": False,
              "error": "Unsupported video file type.",
          }

        try:
          uploaded_map_path, temp_created = self.materializeUploadedVideo(uploaded_map)
        except ValueError as e:
          return {
              "success": False,
              "error": str(e),
          }

      log.info(f"Collected {len(images)} images, calling mapping service")
      # Call mapping service to generate mesh
      # Pass camera IDs in order to ensure correct pose association
      # Treat each camera independently: if a pose exists, anchor it; if not, solve freely

      camera_location_order = []
      camera_order = []
      anchored_cameras = {}  # Track which cameras are anchored: {camera_id: bool}
      serializer = CamSerializer()

      for camera in cameras:
        cam_id = camera.sensor_id
        camera_order.append(cam_id)

        # Check if this camera is calibrated
        is_calibrated = self._is_camera_calibrated(camera, serializer)
        anchored_cameras[cam_id] = is_calibrated

        if is_calibrated:
          # Camera has a calibrated pose - pass it for anchoring
          t = serializer.get_translation(camera)
          q = serializer.get_rotation(camera)
          s = serializer.get_scale(camera) or [1.0, 1.0, 1.0]

          camera_location_order.append({
            "translation": list(t),
            "rotation": list(q),
            "scale": list(s),
          })
          log.info(f"Camera {cam_id} is calibrated, will be anchored in mesh generation")
        else:
          # Camera is uncalibrated - no pose to anchor, will be solved freely
          camera_location_order.append(None)
          log.info(f"Camera {cam_id} is uncalibrated, will be solved freely in mesh generation")

      started = self.mapping_client.startReconstructMesh(
        images, camera_order, camera_location_order, mesh_type, uploaded_map_path
      )
      rid = started.get("request_id")
      if not rid:
        return {"success": False, "error": "mapping service did not return request_id"}

      return {"success": True, "request_id": rid}

    except Exception as e:
      log.error(f"Mesh generation failed: {e}")
      import traceback
      log.error(f"Traceback during mesh generation: {traceback.format_exc()}")
      return {
        "success": False,
        "error": "An internal error occurred while starting mesh generation",
      }

    finally:
      # Cleanup MQTT connection
      try:
        if mqtt_client:
          mqtt_client.disconnect()
      except Exception:
        pass
      # Cleanup temp uploaded map
      try:
        if uploaded_map_path and temp_created:
          os.unlink(uploaded_map_path)
      except Exception:
        pass

  def finalizeMeshFromStatus(self, scene, request_id: str):
    status = self.mapping_client.getReconstructionStatus(request_id)

    if not status.get("success"):
      return {"success": False, "error": status.get("error", "status failed")}

    if status.get("state") != "complete":
      return {"success": False, "error": f"not complete (state={status.get('state')})"}

    mapping_result = (status.get("result") or {})
    if not mapping_result.get("success"):
      return {"success": False, "error": mapping_result.get("error", "reconstruction failed")}

    cameras = scene.sensor_set.filter(type="camera").order_by("id")

    glb_data = mapping_result.get("glb_data")
    if not glb_data:
      return {"success": False, "error": "Mapping service did not return GLB data"}

    # Validate the reconstructed mesh is a single connected scene before
    # mutating any camera poses, so a rejected mesh leaves the scene untouched.
    connectivity_error, merged_mesh = self._checkMeshConnectivity(glb_data)
    if connectivity_error is not None:
      return {"success": False, "error": connectivity_error}

    # Recompute anchored/calibrated state now, before any write-back mutates poses.
    # This is done fresh here rather than reused from startMeshGeneration because
    # that call happens in a separate HTTP request (and often a separate worker
    # process), so any state cached on `self` would not survive to this call.
    serializer = CamSerializer()
    anchored_cameras = {
      camera.sensor_id: self._is_camera_calibrated(camera, serializer)
      for camera in cameras
    }

    self._updateSceneCamerasWithMappingResult(mapping_result, cameras, anchored_cameras)

    # The mapping service builds the GLB from raw world_points in MapAnything's
    # world frame, but returns camera poses already rotated into the Scenescape
    # frame. Mesh and cameras therefore start out in different frames.
    # With anchored cameras we know their true scene pose, so align the mesh onto
    # them (moving the mesh, not the trusted cameras). Without any anchor there is
    # no reference, so fall back to the geometric floor-fit heuristic.
    has_anchors = any(anchored_cameras.values())
    if has_anchors:
      mesh_to_scene, _ = self._computeAnchorMeshTransform(
        mapping_result, cameras, anchored_cameras, serializer)
      if mesh_to_scene is not None:
        merged_mesh.apply_transform(mesh_to_scene)
      self._saveMeshToScene(scene, merged_mesh, align=False)
    else:
      mesh_transform = self._saveMeshToScene(scene, merged_mesh, align=True)
      if mesh_transform is not None:
        self._transformCamerasWithMeshAlignment(cameras, mesh_transform, anchored_cameras)

    # Identify unanchored cameras for user warning
    unanchored_cameras = [cam_id for cam_id, is_anchored in anchored_cameras.items() if not is_anchored]
    result = {"success": True}
    if unanchored_cameras:
      result["unanchored_cameras"] = unanchored_cameras
      log.info(f"Mesh generation complete. Unanchored cameras (no prior calibration): {unanchored_cameras}")

    return result

  def _updateSceneCamerasWithMappingResult(self, mapping_result, cameras, anchored_cameras=None):
    """
    Update scene cameras with poses and intrinsics returned by mapping service.

    For cameras that were anchored (had a calibrated pose before generation),
    skip the pose/intrinsics write-back to preserve the trusted calibration.
    For uncalibrated cameras, apply the MapAnything estimates.

    Args:
      mapping_result: Result from mapping service containing camera_poses and intrinsics
      cameras: QuerySet of camera objects in enumeration order
      anchored_cameras: Dict mapping camera_id -> bool (True if camera was anchored)
    """
    if anchored_cameras is None:
      anchored_cameras = {}

    try:
      camera_poses_raw = mapping_result.get("camera_poses", [])
      intrinsics_raw = mapping_result.get("intrinsics", [])

      pose_by_id = {}
      for p in camera_poses_raw:
        if not isinstance(p, dict):
          continue
        cid = p.get("camera_id")
        if cid is None:
          continue
        pose_by_id[cid] = p

      if not pose_by_id:
        log.warning("Mapping service returned no camera poses with camera_id")
        return

      intrinsics_by_id = {}

      if intrinsics_raw and isinstance(intrinsics_raw[0], dict):
        for item in intrinsics_raw:
          cid = item.get("camera_id")
          K = item.get("K")
          if cid is None or K is None:
            continue
          intrinsics_by_id[cid] = K

      cameras_list = list(cameras)
      log.info(f"Updating cameras using camera_id matching. Cameras in scene: {len(cameras_list)}")

      # Update each camera with corresponding pose and intrinsics
      for camera in cameras_list:
        try:
          cam_id = camera.sensor_id
          pose_data = pose_by_id.get(cam_id)
          intrinsics_matrix = intrinsics_by_id.get(cam_id)

          if pose_data is None:
            log.warning(f"No pose for camera {cam_id}, skipping")
            continue

          if intrinsics_matrix is None:
            log.warning(f"No intrinsics for camera {cam_id}, skipping intrinsics update")

          # Check if this camera was anchored (calibrated before generation)
          was_anchored = anchored_cameras.get(cam_id, False)

          if was_anchored:
            # Camera was anchored - skip write-back to preserve the trusted calibration
            log.info(f"Camera {cam_id} was anchored, preserving calibrated pose (skipping write-back)")
            continue

          # Uncalibrated camera: its estimated pose is only a guess, so leave the
          # camera at its default pose and let the warning prompt a real calibration.
          log.info(f"Camera {cam_id} is uncalibrated, leaving pose at default (intrinsics only)")
          self._updateCameraIntrinsics(camera, intrinsics_matrix)
        except Exception as e:
          log.error(f"Failed to update camera {camera.sensor_id}: {e}")

    except Exception as e:
      log.error(f"Failed to update scene cameras: {e}")

  def _updateCameraIntrinsics(self, camera, intrinsics_matrix):
    """Update only the intrinsics of a camera, leaving its pose untouched."""
    if intrinsics_matrix is None:
      return

    try:
      intrinsics_array = np.array(intrinsics_matrix)
      camera.cam.intrinsics_fx = intrinsics_array[0, 0]
      camera.cam.intrinsics_fy = intrinsics_array[1, 1]
      camera.cam.intrinsics_cx = intrinsics_array[0, 2]
      camera.cam.intrinsics_cy = intrinsics_array[1, 2]
      camera.cam.save()
    except Exception as e:
      log.error(f"Error updating intrinsics for camera {camera.sensor_id}: {e}")

  def _computeAnchorMeshTransform(self, mapping_result, cameras, anchored_cameras, serializer):
    """
    Compute the transform that brings the reconstructed mesh into the scene frame,
    using the anchored cameras' known poses as the reference.

    The mapping service exports the mesh in MapAnything's world frame but returns
    camera poses already rotated by 180 degrees about X into the Scenescape frame.
    Undoing that rotation puts the mesh in the same frame as the returned poses;
    any remaining drift is then removed by matching each anchored camera's returned
    pose to its true calibrated pose.

    Returns:
      tuple: (mesh_to_scene, correction) as a 4x4 matrix and a mesh_transform-style
        dict, or (None, None) if no usable anchor was found.
    """
    # 180 degrees about X, matching the rotation the mapping service applies to poses.
    frame_flip = np.diag([1.0, -1.0, -1.0, 1.0])

    pose_by_id = {p["camera_id"]: p for p in mapping_result.get("camera_poses", [])
                  if isinstance(p, dict) and p.get("camera_id") is not None}

    scene_mats = []
    returned_mats = []
    for camera in cameras:
      cam_id = camera.sensor_id
      if not anchored_cameras.get(cam_id, False):
        continue

      pose_data = pose_by_id.get(cam_id)
      if pose_data is None:
        continue

      try:
        translation = serializer.get_translation(camera)
        euler_rotation = serializer.get_rotation(camera)
        if translation is None or euler_rotation is None:
          continue

        scene_mat = np.eye(4)
        scene_mat[:3, :3] = Rotation.from_euler('XYZ', euler_rotation, degrees=True).as_matrix()
        scene_mat[:3, 3] = translation

        returned_mat = np.eye(4)
        returned_mat[:3, :3] = Rotation.from_quat(pose_data['rotation']).as_matrix()
        returned_mat[:3, 3] = pose_data['translation']

        scene_mats.append(scene_mat)
        returned_mats.append(returned_mat)
      except Exception as e:
        log.warning(f"Could not use anchored camera {cam_id} for mesh alignment: {e}")

    if not scene_mats:
      log.warning("No usable anchored camera pose for mesh alignment, applying frame flip only")
      return frame_flip, None

    corrections = [s @ np.linalg.inv(r) for s, r in zip(scene_mats, returned_mats)]

    correction_mat = np.eye(4)
    correction_mat[:3, :3] = Rotation.from_matrix(
      np.array([c[:3, :3] for c in corrections])).mean().as_matrix()
    correction_mat[:3, 3] = np.mean([c[:3, 3] for c in corrections], axis=0)

    log.info(f"Aligning mesh onto {len(corrections)} anchored camera(s), "
             f"residual translation={correction_mat[:3, 3]}")

    correction = {
      'rotation_matrix': correction_mat[:3, :3],
      'translation': correction_mat[:3, 3],
      'center_offset': np.zeros(3),
    }
    return correction_mat @ frame_flip, correction

  def _saveMeshToScene(self, scene, merged_mesh, align=True):
    """
    Save the generated GLB mesh to the scene's map field.

    Args:
      scene: Scene object to update
      merged_mesh: Pre-loaded, merged trimesh object from _checkMeshConnectivity
      align: If True, apply the floor-fit heuristic (alignMeshToXYPlane). If False,
        save the mesh as returned by the mapping service, without any realignment.

    Returns:
      dict: Transformation applied to mesh (rotation matrix, translation, center_offset),
        or None if align is False (no camera transform is needed in that case).
    """
    try:
      if align:
        # Align the mesh to XY plane with largest bottom face flat and in first quadrant
        log.info(f"Aligning mesh to XY plane in first quadrant")
        aligned_mesh, mesh_transform = self.alignMeshToXYPlane(merged_mesh)
      else:
        log.info("Anchored camera(s) present, saving mesh as returned by mapping service")
        aligned_mesh, mesh_transform = merged_mesh, None

      # Export the aligned mesh as GLB
      glb_filename = f"{scene.name}_generated_mesh.glb"
      glb_exported_bytes = aligned_mesh.export(file_type='glb')

      log.info(f"Saving aligned mesh to scene {scene.name} as {glb_filename}")
      # Save to scene's map field without triggering save yet
      scene.map.save(glb_filename, ContentFile(glb_exported_bytes), save=False)

      # Update the map_processed timestamp
      scene.map_processed = get_iso_time()
      scene._original_map = None
      # Set flag to indicate mesh is from generateMesh flow (already aligned by mapping service)
      scene._from_generate_mesh = True
      scene.save()

      log.info(f"Saved generated mesh to scene {scene.name}")

      return mesh_transform

    except Exception as e:
      log.error(f"Failed to save mesh to scene: {e}")
      raise Exception(f"Failed to save mesh file: {e}")

  def _transformCamerasWithMeshAlignment(self, cameras, mesh_transform, anchored_cameras=None):
    """
    Apply the same transformation to cameras that was applied to the mesh.
    This maintains the relative pose between cameras and mesh.

    Anchored cameras are skipped: their pose is already trusted scene-space
    calibration, not raw mapping-service output, so it must not be re-aligned.

    Args:
      cameras: QuerySet of camera objects to transform
      mesh_transform: Dictionary containing:
        - 'rotation_matrix': 3x3 rotation matrix applied to mesh
        - 'translation': Translation vector applied to mesh after rotation
        - 'center_offset': Centering offset applied to mesh
      anchored_cameras: Dict mapping camera_id -> bool (True if camera was anchored)
    """
    if anchored_cameras is None:
      anchored_cameras = {}

    try:
      rotation_matrix = mesh_transform['rotation_matrix']
      translation = mesh_transform['translation']
      center_offset = mesh_transform['center_offset']

      log.info(f"Transforming {cameras.count()} cameras to match mesh alignment")

      for camera in cameras:
        try:
          if anchored_cameras.get(camera.sensor_id, False):
            log.info(f"Camera {camera.sensor_id} was anchored, skipping mesh-alignment transform")
            continue

        # Get current camera transform (in QUATERNION format)
        # Format: [tx, ty, tz, qx, qy, qz, qw, sx, sy, sz]
          cam_transforms = camera.cam.transforms

          if not cam_transforms or len(cam_transforms) < 10:
            log.warning(f"Camera {camera.sensor_id} has invalid transforms, skipping")
            continue

          current_position = np.array([cam_transforms[0], cam_transforms[1], cam_transforms[2]])
          current_quat_xyzw = np.array([cam_transforms[3], cam_transforms[4], cam_transforms[5], cam_transforms[6]])
          current_rotation = Rotation.from_quat(current_quat_xyzw).as_matrix()

          rotated_position = rotation_matrix @ current_position
          translated_position = rotated_position + translation
          final_position = translated_position - center_offset
          final_rotation = rotation_matrix @ current_rotation
          final_quat_xyzw = Rotation.from_matrix(final_rotation).as_quat()

          # Update camera transforms
          camera.cam.transforms = [
            final_position[0], final_position[1], final_position[2],  # translation
            final_quat_xyzw[0], final_quat_xyzw[1], final_quat_xyzw[2], final_quat_xyzw[3],  # quaternion [x, y, z, w]
            cam_transforms[7], cam_transforms[8], cam_transforms[9]  # scale (preserve original)
          ]

          camera.cam.save()
          log.info(f"Transformed camera {camera.sensor_id}")

        except Exception as e:
          log.error(f"Failed to transform camera {camera.sensor_id}: {e}")

      log.info(f"Successfully transformed all cameras to match mesh alignment")

    except Exception as e:
      log.error(f"Failed to transform cameras with mesh alignment: {e}")
      raise

  def _extractLargestBottomFaceNormal(self, mesh):
    """
    Extract the normal vector of the largest face of the OBB that is oriented towards the negative Z direction.

    Args:
      mesh: trimesh object

    Returns:
      numpy array: Normal vector of the largest bottom face
    """
    to_origin, extents = trimesh.bounds.oriented_bounds(mesh)

    # The to_origin matrix transforms the mesh into OBB coordinates
    # We need the inverse to get OBB axes in world coordinates
    from_origin = np.linalg.inv(to_origin)
    R = from_origin[:3, :3]
    obb_center = from_origin[:3, 3]

    log.info(f"OBB center: {obb_center}, extents: {extents}")

    # OBB has 6 faces (pairs of parallel faces along 3 axes)
    # Face normals in OBB coordinate system are the 3 axis directions
    # We need to find which face is largest and farthest in -ve Z direction

    # The 3 axes of the OBB in world coordinates are the columns of R
    # Face areas are products of two extent dimensions
    face_areas = [
      extents[1] * extents[2],  # Face perpendicular to axis 0 (X-axis of OBB)
      extents[0] * extents[2],  # Face perpendicular to axis 1 (Y-axis of OBB)
      extents[0] * extents[1]   # Face perpendicular to axis 2 (Z-axis of OBB)
    ]

    # For each axis, we have two faces (positive and negative direction)
    # Compute the center of each face and its Z coordinate
    faces = []
    for axis_idx in range(3):
      # Normal vector in world coordinates for this axis
      normal = R[:, axis_idx]

      # Two face centers along this axis
      for direction in [-1, 1]:
        face_center = obb_center + direction * (extents[axis_idx] / 2.0) * normal
        faces.append({
          'axis_idx': axis_idx,
          'direction': direction,
          'normal': normal * direction,
          'center': face_center,
          'area': face_areas[axis_idx],
          'z_position': face_center[2]
        })

    # Find the largest face that is farthest in the -ve z direction
    # Sort by area (descending) then by z_position (ascending for most negative)
    faces.sort(key=lambda f: (-f['area'], f['z_position']))

    target_face = faces[0]
    log.info(f"Selected face: axis={target_face['axis_idx']}, area={target_face['area']:.2f}, "
          f"z_pos={target_face['z_position']:.2f}, normal={target_face['normal']}")

    # Ensure the normal points upward (+Z direction)
    normal = target_face['normal']
    normal = normal / np.linalg.norm(normal)
    if normal[2] < 0:
      normal = -normal

    return normal

  def _computeAlignmentRotation(self, target_normal):
    """
    Compute rotation matrix to align target normal with Z-axis.
    """
    z_axis = np.array([0.0, 0.0, 1.0])
    rotation_axis = np.cross(target_normal, z_axis)
    rotation_axis_norm = np.linalg.norm(rotation_axis)

    if rotation_axis_norm > 1e-6:
      rotation_axis = rotation_axis / rotation_axis_norm
      rotation_angle = np.arccos(np.clip(np.dot(target_normal, z_axis), -1.0, 1.0))
      rotation = Rotation.from_rotvec(rotation_angle * rotation_axis)
      rotation_matrix = rotation.as_matrix()
    else:
      # Target normal is already aligned with Z-axis
      if target_normal[2] > 0:
        rotation_matrix = np.eye(3)
      else:
        # Need to flip 180 degrees
        rotation_matrix = np.diag([1, 1, -1])

    return rotation_matrix

  def alignMeshToXYPlane(self, mesh_data):
    """
    Align mesh such that the largest face farthest in the -ve z direction is flat on the XY plane.

    This method:
    1. Computes the oriented bounding box (OBB) of the mesh
    2. Identifies the largest face of the OBB that is farthest in the negative Z direction
    3. Rotates and translates the mesh so that face lies flat on the XY plane (z=0)
    4. Moves the mesh to the first quadrant (all vertices have x,y,z >= 0)

    Args:
      mesh_data: Either a trimesh object or bytes/BytesIO of a mesh file (GLB, PLY, etc.)

    Returns:
      tuple: (aligned_mesh, transform_dict) where transform_dict contains:
        - 'rotation_matrix': 3x3 rotation matrix applied
        - 'translation': Translation vector applied after rotation
        - 'center_offset': Centering offset applied (zero in this case)
    """
    try:
      if isinstance(mesh_data, (bytes, BytesIO)):
        mesh = trimesh.load(BytesIO(mesh_data) if isinstance(mesh_data, bytes) else mesh_data, file_type='glb')
      else:
        mesh = mesh_data

      # Get the largest bottom face normal (already normalized and pointing upward)
      target_normal = self._extractLargestBottomFaceNormal(mesh)

      # Compute rotation to align target normal with Z-axis
      rotation_matrix = self._computeAlignmentRotation(target_normal)
      rotation_transform = np.eye(4)
      rotation_transform[:3, :3] = rotation_matrix
      mesh.apply_transform(rotation_transform)

      # Compute translation to move the mesh entirely to first quadrant (+x, +y) and z=0
      # Find the minimum values along each axis after rotation
      bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
      min_x, min_y, min_z = bounds[0]

      translation = np.array([-min_x, -min_y, -min_z])
      translation_transform = np.eye(4)
      translation_transform[:3, 3] = translation
      mesh.apply_transform(translation_transform)

      # Verify the mesh is in the first quadrant
      final_bounds = mesh.bounds
      final_min = final_bounds[0]
      final_max = final_bounds[1]

      log.info(f"Mesh aligned to first quadrant: bbox min={final_min}, max={final_max}")

      transform_dict = {
        'rotation_matrix': rotation_matrix,
        'translation': translation,
        'center_offset': np.array([0.0, 0.0, 0.0])
      }

      return mesh, transform_dict

    except Exception as e:
      log.error(f"Failed to align mesh to XY plane: {e}")
      raise
