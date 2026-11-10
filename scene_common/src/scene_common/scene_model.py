# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import os
from copy import copy
from threading import RLock

from scene_common import log
from scene_common.camera import Camera
from scene_common.mesh_util import extractTriangleMesh, getMeshAxisAlignedProjectionToXY, getPosedMeshFootprint
from scene_common.options import (
  POSE_CLASS_LIVE,
  POSE_ORIGIN_DETECTOR_EXTRINSICS,
  make_pose_provenance,
  pose_is_live,
  sync_legacy_pose_source,
)
from scene_common.transform import (
  CameraIntrinsics, CameraPose, validate_camera_extrinsics,
)

IMAGE_MAP_TYPES = ["png", "jpg", "jpeg"]


def _normalize_observation_resolution(resolution):
  """Return [width, height] integers or raise ValueError."""
  if isinstance(resolution, dict):
    resolution = [resolution.get('width'), resolution.get('height')]
  if (not isinstance(resolution, (list, tuple)) or len(resolution) != 2
      or not all(type(value) is int and value > 0 for value in resolution)):
    raise ValueError(f"Invalid sensor resolution: {resolution!r}")
  return list(resolution)


def _observation_intrinsics_values(intrinsics):
  """Return fx,fy,cx,cy from an MQTT intrinsics dict or 4-list."""
  if isinstance(intrinsics, dict):
    values = CameraIntrinsics.intrinsicsDictToList(intrinsics)
  elif isinstance(intrinsics, (list, tuple)) and len(intrinsics) == 4:
    values = list(intrinsics)
  else:
    raise ValueError(f"Invalid observation intrinsics: {intrinsics!r}")
  if len(values) != 4:
    # FoV forms need resolution; reject here rather than inventing policy.
    raise ValueError(f"Observation intrinsics must provide fx,fy,cx,cy: {intrinsics!r}")
  return tuple(float(value) for value in values)


def _copy_camera_intrinsics(intrinsics):
  """Deep-copy CameraIntrinsics so retained/observation poses do not share arrays."""
  distortion = getattr(intrinsics, 'distortion', None)
  return CameraIntrinsics(
    intrinsics.intrinsics.copy(),
    None if distortion is None else distortion.copy(),
  )


def _merge_observation_optics(current, intrinsics=None, distortion=None, resolution=None):
  """Build CameraIntrinsics for an MQTT observation, or None if optics omitted.

  Resolution alone does not invent a principal point from width/height; send
  explicit ``intrinsics`` (or ``distortion``) when changing runtime optics.
  Invalid resolution still raises so callers can ignore the whole optics update.
  """
  if intrinsics is None and distortion is None and resolution is None:
    return None
  if resolution is not None:
    resolution = _normalize_observation_resolution(resolution)
  if intrinsics is None and distortion is None:
    return None
  matrix = current.intrinsics
  fx, fy = float(matrix[0, 0]), float(matrix[1, 1])
  cx, cy = float(matrix[0, 2]), float(matrix[1, 2])
  if intrinsics is not None:
    fx, fy, cx, cy = _observation_intrinsics_values(intrinsics)
  dist = current.distortion if distortion is None else distortion
  return CameraIntrinsics({'fx': fx, 'fy': fy, 'cx': cx, 'cy': cy}, dist, resolution)


class SceneModel:
  def __init__(self, name, map_file, scale=None):
    self.name = name
    self.background = None
    self.map_triangle_mesh = None
    self.map_file = map_file
    self._loadMapData(map_file, scale)
    self.children = []
    self.cameras = {}
    self._camera_lock = RLock()
    self.regions = {}
    self.tripwires = {}
    self.sensors = {}
    self.events = {}
    self.output_lla = False
    self.map_corners_lla = None
    self.use_tracker = True

    self.mesh_translation = None
    self.mesh_rotation = None
    self.mesh_scale = None
    self.scale = scale
    return

  def _loadMapData(self, map_file, scale):
    """Load the background image and triangle mesh for map_file when it exists on disk."""
    if not map_file:
      return
    # FIXME: get the image binary data using url rather than this hack
    if 'http' in map_file:
      map_file = map_file.replace('https://web.scenescape.intel.com', '/home/scenescape/Scenescape')
    if os.path.exists(map_file):
      self.background = cv2.imread(map_file)
      self.extractMapTriangleMesh(map_file, scale)

  def reloadMapIfChanged(self, map_file, scale):
    """Reload the map when its file or scale differs from the loaded one.

    Hydration updates a scene in place, so a map swapped from an image to a GLB
    (or back) must replace the background and triangle mesh; otherwise the
    footprint and TRS-to-LLA transform keep describing the old map.
    Call before self.scale is updated to the new value.
    """
    if map_file == self.map_file and scale == self.scale:
      return False
    self.map_file = map_file
    self.background = None
    self.map_triangle_mesh = None
    self._loadMapData(map_file, scale)
    return True

  def extractMapTriangleMesh(self, mapFile, scale):
    map_info = []
    if os.path.basename(mapFile).split(".")[-1].lower() in IMAGE_MAP_TYPES:
      if not scale:
        log.error("Scale not provided with a map image")
        return
      map_info.append(mapFile)
      map_info.append(scale)
    else:
      map_info.append(mapFile)

    self.map_triangle_mesh, _ = extractTriangleMesh(map_info)

    return

  def cameraWithID(self, anID):
    if anID in self.cameras:
      return self.cameras[anID]
    return None

  def updateCameras(self, newCameras):
    with self._camera_lock:
      cameras = {}
      for cameraData in newCameras:
        camera_id = cameraData['uid']
        camera = Camera(camera_id, cameraData, resolution=cameraData['resolution'])
        previous = self.cameras.get(camera_id)
        self._retainObservedPose(camera, previous)
        cameras[camera_id] = camera
      self.cameras = cameras

  @staticmethod
  def _retainObservedPose(camera, previous):
    if (not getattr(camera, 'pose_locked', False)
        and previous is not None
        and not getattr(previous, 'pose_locked', False)
        and pose_is_live(previous)
        and getattr(camera, 'pose', None) is not None
        and getattr(previous, 'pose', None) is not None):
      # Keep live pose and MQTT optics; do not take refreshed config optics.
      camera.pose = CameraPose(
        previous.pose.pose_mat.copy(),
        _copy_camera_intrinsics(previous.pose.intrinsics))
      previous_provenance = getattr(previous, 'pose_provenance', None)
      if isinstance(previous_provenance, dict):
        camera.pose_provenance = dict(previous_provenance)
      else:
        camera.pose_provenance = make_pose_provenance(
          POSE_CLASS_LIVE, POSE_ORIGIN_DETECTOR_EXTRINSICS)
      sync_legacy_pose_source(camera)

  def retainObservedCameraPoses(self, previous_scene):
    """Transfer eligible observed poses from a replaced scene instance."""
    with self._camera_lock:
      previous_cameras = getattr(previous_scene, 'cameras', {})
      for camera_id, camera in self.cameras.items():
        self._retainObservedPose(camera, previous_cameras.get(camera_id))

  def updateCameraPose(self, camera_id, extrinsics,
                       origin=POSE_ORIGIN_DETECTOR_EXTRINSICS):
    """Replace an observation-authorized pose without changing durable calibration."""
    self.updateCameraObservation(
      camera_id, extrinsics=extrinsics, origin=origin)

  def updateCameraObservation(
      self, camera_id, extrinsics=None, intrinsics=None, distortion=None,
      resolution=None, origin=POSE_ORIGIN_DETECTOR_EXTRINSICS):
    """Apply unlocked MQTT extrinsics and/or optics without durable writes."""
    with self._camera_lock:
      current = self.cameras.get(camera_id)
      if (current is None or getattr(current, 'pose', None) is None
          or getattr(current, 'pose_locked', False)):
        return
      optics = _merge_observation_optics(
        current.pose.intrinsics, intrinsics, distortion, resolution)
      if extrinsics is None and optics is None:
        return
      if extrinsics is not None:
        pose = CameraPose(
          validate_camera_extrinsics(extrinsics),
          optics if optics is not None else _copy_camera_intrinsics(
            current.pose.intrinsics))
        provenance = make_pose_provenance(POSE_CLASS_LIVE, origin)
      else:
        pose = CameraPose(current.pose.pose_mat.copy(), optics)
        provenance = getattr(current, 'pose_provenance', None)
      camera = copy(current)
      camera.pose = pose
      camera.pose_locked = False
      if isinstance(provenance, dict):
        camera.pose_provenance = dict(provenance)
      sync_legacy_pose_source(camera)
      self.cameras[camera_id] = camera

  def cameraSnapshot(
      self, camera_id=None, extrinsics=None, intrinsics=None, distortion=None,
      resolution=None, origin=POSE_ORIGIN_DETECTOR_EXTRINSICS):
    """Apply an MQTT observation and capture stable camera entries under one lock."""
    with self._camera_lock:
      if camera_id is not None:
        try:
          self.updateCameraObservation(
            camera_id, extrinsics=extrinsics, intrinsics=intrinsics,
            distortion=distortion, resolution=resolution, origin=origin)
        except (TypeError, ValueError) as exc:
          log.warning(f"Ignoring invalid camera metadata for {camera_id}: {exc}")
      observation = copy(self)
      observation.cameras = dict(self.cameras)
      return observation

  def serialize(self):
    data = {
      'uid': self.name,
      'name': self.name,
      'output_lla': self.output_lla,
      'map_corners_lla': self.map_corners_lla,
      'use_tracker': self.use_tracker
    }

    # children
    # current objects/things

    if self.cameras:
      data['cameras'] = {x: self.cameras[x].serialize() for x in self.cameras}
    if self.sensors:
      data['sensors'] = {x: self.sensors[x].serialize() for x in self.sensors}
    if self.regions:
      data['regions'] = {x: self.regions[x].serialize() for x in self.regions}
    if self.tripwires:
      data['tripwires'] = {x: self.tripwires[x].serialize() for x in self.tripwires}

    return data

  def areCoordinatesInPixels(self, pixelCoords):
    if self.background is None or self.scale is None:
      return False
    bgRes = self.background.shape[1::-1]
    maxMetersX = bgRes[0] / self.scale
    maxMetersY = bgRes[1] / self.scale
    for pt in pixelCoords:
      if pt[0] is not None and pt[1] is not None \
         and (pt[0] > 2 * maxMetersX or pt[1] > 2 * maxMetersY):
        return True
    return False

  def mapPixelsToMetric(self, pixelCoords):
    if self.background is None:
      return pixelCoords
    bgRes = self.background.shape[1::-1]
    points = [[c[0] / self.scale, (bgRes[1] - c[1]) / self.scale] for c in pixelCoords]
    return points

  def mapFootprintCorners(self):
    """! Map footprint corners (SW, SE, NE, NW at z=0) in the scene's local frame.

    Image maps are already in that frame. A GLB mesh is stored unposed, so the
    scene's mesh scale, rotation and translation must be applied first. Without the
    rotation and translation the unposed footprint would be in the wrong frame, so a
    ValueError is raised rather than returning it silently.
    """
    ext = os.path.splitext(self.map_file or "")[1].lower()[1:]
    if ext in IMAGE_MAP_TYPES:
      return getMeshAxisAlignedProjectionToXY(self.map_triangle_mesh)
    if self.mesh_rotation is None or self.mesh_translation is None:
      raise ValueError(f"Scene '{self.name}' has a GLB map without mesh_rotation/mesh_translation; "
                       "the footprint cannot be placed in the scene frame")
    return getPosedMeshFootprint(self.map_triangle_mesh, self.mesh_rotation, self.mesh_translation,
                                 self.mesh_scale)
