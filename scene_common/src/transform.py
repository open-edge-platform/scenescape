# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import math

import cv2
import numpy as np
import open3d as o3d

from scene_common import log
from scipy.spatial.transform import Rotation
from scene_common.geometry import isarray, Point, Line, Rectangle, Region

MAX_COPLANAR_DETERMINANT = 0.1

class CameraIntrinsics:
  INTRINSICS_KEYS = ('fx', 'fy', 'cx', 'cy')
  DISTORTION_KEYS = ('k1', 'k2', 'p1', 'p2', 'k3', 'k4', 'k5', 'k6',
                     's1', 's2', 's3', 's4', 'taux', 'tauy')

  def __init__(self, intrinsics, distortion=None, resolution=None):
    if isinstance(intrinsics, dict):
      intrinsics = self.intrinsicsDictToList(intrinsics)

    fov = None
    if isarray(intrinsics):
      if len(intrinsics) == 1 or len(intrinsics) == 2:
        fov = intrinsics
      elif len(intrinsics) == 4:
        intrinsics = [[intrinsics[0], 0.0, intrinsics[2]],
                      [0.0, intrinsics[1], intrinsics[3]],
                      [0.0, 0.0, 1.0]]
    else:
      fov = intrinsics

    if fov is not None:
      intrinsics = self.computeIntrinsicsFromFoV(resolution, fov)

    if not isarray(intrinsics) or not len(intrinsics):
      raise ValueError("Invalid intrinsics", intrinsics)

    self.intrinsics = np.array(intrinsics)
    self._setDistortion(distortion)
    return

  def _setDistortion(self, distortion):
    if distortion is not None:
      if isarray(distortion):
        if len(distortion) not in [4, 5, 8, 12, 14]:
          raise ValueError("Bad distortion value:", distortion)
        distortion = np.pad(np.array(distortion, dtype=np.float64),
                          (0, 14 - len(distortion)), constant_values=0.0)
      elif isinstance(distortion, dict):
        distortion = np.array(self.distortionDictToList(distortion), dtype=np.float64)
      else:
        raise TypeError("Unsupported distortion type", type(distortion))
    else:
      distortion = np.zeros(14)
    self.distortion = distortion

  def computeIntrinsicsFromFoV(self, resolution, fov):
    if not isarray(resolution) or len(resolution) != 2:
      raise ValueError("Resolution required to calculate intrinsics from field of view")
    cx = resolution[0] / 2
    cy = resolution[1] / 2
    d = math.sqrt(cx * cx + cy * cy)
    fx = fy = None

    fov = self._parseFOV(fov)
    fy, fx = self._calculateFocalLengths(cx, cy, d, fov)
    intrinsics = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])
    if cx == 0 or cy == 0 or fx == 0 or fy == 0:
      raise ValueError("Invalid intrinsics", intrinsics)
    return intrinsics

  def _parseFOV(self, fov):
    if isinstance(fov, (list, tuple)):
      return fov
    elif isinstance(fov, str):
      return fov.split(':') if ':' in fov else fov.split('x')
    return [fov]

  def _calculateFocalLengths(self, cx, cy, d, fov):
    if len(fov) == 1:
      fx = fy = d / math.tan(math.radians(float(fov[0]) / 2))
    else:
      if not isinstance(fov[0], str) or len(fov[0]):
        fx = cx / math.tan(math.radians(float(fov[0]) / 2))
      if not isinstance(fov[1], str) or len(fov[1]):
        fy = cy / math.tan(math.radians(float(fov[1]) / 2))
      if fx is None:
        fx = fy
      if fy is None:
        fy = fx
    return fy, fx

  def pinholeUndistort(self, image):
    """Undistort image using pinhole camera model"""
    if np.any(self.distortion != 0):
      h, w = image.shape[:2]
      map_x, map_y = cv2.initUndistortRectifyMap(
        self.intrinsics, self.distortion, None, self.intrinsics, (w, h), 5)
      image_undistort = cv2.remap(image, map_x, map_y, cv2.INTER_LINEAR)

      return image_undistort
    return image

  def _createUndistortIntrinsics(self, resolution):
    new_intrins = self.intrinsics.copy()
    new_intrins[0, 2] += resolution[0] / 2
    new_intrins[1, 2] += resolution[1] / 2
    self.undistort_intrinsics = new_intrins

  def unwarp(self, image):
    """Unwarp image pixels using fisheye camera model"""
    if not hasattr(self, "map1"):
      h, w = image.shape[:2]
      self._createUndistortIntrinsics((w, h))
      self.map1, self.map2 = cv2.fisheye.initUndistortRectifyMap(
        self.intrinsics, self.distortion[:4], np.eye(3), self.undistort_intrinsics,
        (w*2, h*2), cv2.CV_16SC2)

    new_image = cv2.remap(image, self.map1, self.map2, interpolation=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT)

    if not hasattr(self, "crop"):
      mask = np.any(new_image != [0,0,0], axis=-1)
      rows = mask.any(0)
      cols = mask.any(1)
      y1 = cols.argmax()
      x1 = rows.argmax()
      y2 = mask.shape[0]-cols[::-1].argmax()
      x2 = mask.shape[1]-rows[::-1].argmax()
      self.crop = [y1, y2, x1, x2]

      # Cache intrinsics that match the unwarped image
      self.unwarpIntrinsics = self.intrinsics.copy()
      uh = y2 - y1
      uw = x2 - x1
      self.unwarpIntrinsics[0, 2] = uw / 2
      self.unwarpIntrinsics[1, 2] = uh / 2
      self.unwarpIntrinsics[0, 0] = uw * self.unwarpIntrinsics[0, 0] / w
      self.unwarpIntrinsics[1, 1] = uh * self.unwarpIntrinsics[1, 1] / h

    new_image = new_image[self.crop[0]:self.crop[1], self.crop[2]:self.crop[3]]

    return new_image

  def rewarpPoint(self, point):
    """Apply distortion to a point using the fisheye camera model"""
    if isinstance(point, Point):
      point = point.as2Dxy.asNumpyCartesian
    inverted = np.linalg.inv(self.undistort_intrinsics)
    pt = np.array([point[0] + self.crop[2], point[1] + self.crop[0], 1]).reshape(3, 1)
    pt = np.matmul(inverted, pt)[:2].reshape(-1, 1, 2)
    return Point(cv2.fisheye.distortPoints(pt, self.intrinsics,
                                           self.distortion).reshape(-1, 2))

  def infer3DCoordsFrom2DDetection(self, coords, distance=None):
    """Convert pixel coordinates to normalized image plane of the camera
    @param coords Rectangle or Point in pixel coordinates
    """
    if coords.is3D:
      log.debug("Coordinate is already 3D", coords)
      return coords

    if isinstance(coords, Rectangle):
      origin = self.infer3DCoordsFrom2DDetection(coords.origin, distance)
      opposite = self.infer3DCoordsFrom2DDetection(coords.opposite, distance)
      return Rectangle(origin=origin, opposite=opposite)

    undistorted_pt = cv2.undistortPoints(coords.as2Dxy.asNumpyCartesian.reshape(-1, 1, 2),
                                         self.intrinsics, self.distortion)
    pt = Point(np.squeeze(undistorted_pt))
    if distance is not None:
      if math.isnan(distance):
        raise ValueError("Invalid distance", distance)
      pt = Point(pt.x * distance, pt.y * distance, distance)
    if math.isnan(pt.x) or math.isnan(pt.y):
      raise ValueError("Invalid Point", pt.x, pt.y)
    return pt

  def asDict(self):
    # FIXME - find a way to return fov and hfov/vfov if that is how
    # the user originally specified the intrinsics
    iData = {
      'intrinsics': {
        'fx': self.intrinsics[0][0],
        'fy': self.intrinsics[1][1],
        'cx': self.intrinsics[0][2],
        'cy': self.intrinsics[1][2],
      },
      'distortion': dict(zip(self.DISTORTION_KEYS, self.distortion)),
    }

    return iData

  @staticmethod
  def intrinsicsDictToList(iDict):
    if all(key in iDict for key in CameraIntrinsics.INTRINSICS_KEYS):
      iList = [iDict[key] for key in CameraIntrinsics.INTRINSICS_KEYS]
    elif all(key in iDict for key in ('hfov', 'vfov')):
      iList = [iDict['hfov'], iDict['vfov']]
    elif 'fov' in iDict:
      iList = [iDict['fov']]
    else:
      raise ValueError("Invalid intrinsics:", iDict)
    return iList

  @staticmethod
  def distortionDictToList(dDict):
    dList = []
    for key in CameraIntrinsics.DISTORTION_KEYS:
      if key not in dDict:
        dList.append(0.0)
      else:
        dList.append(dDict[key])
    return dList

class CameraPose:
  def __new__(cls, pose, intrinsics):
    """Represents a camera pose with the ability to move points from
    camera coordinate system to world coordinate system.

    @param    pose         information describing pose
    @param    intrinsics   instance of CameraIntrinsics

    Pose information can be one of 4 formats:
      - matrix
      - quaternion rotation, translation, scale
      - euler rotation, translation, scale
      - 3d-2d point correspondence
    """

    if cls == CameraPose and isinstance(pose, dict) \
       and 'camera points' in pose and 'map points' in pose:
      return PointCorrespondenceTransform(pose, intrinsics)
    return super().__new__(cls)

  def __init__(self, pose, intrinsics):
    """Represents a camera pose with the ability to move points from
    camera coordinate system to world coordinate system.

    @param    pose         information describing pose
    @param    intrinsics   instance of CameraIntrinsics

    Pose information can be one of 3 formats:
      - matrix
      - quaternion rotation, translation, scale
      - euler rotation, translation, scale
    """

    self.intrinsics = intrinsics
    self.setPose(pose)
    return

  def setPose(self, pose):
    """Set the pose of the camera"""
    if isinstance(pose, np.ndarray) and (pose.shape == (3, 4) or pose.shape == (4, 4)):
      if pose.shape == (3, 4):
        pose = np.vstack((pose, [0, 0, 0, 1]))
      self.pose_mat = pose
    elif isinstance(pose, dict) \
        and all(k in pose for k in ('translation', 'rotation', 'scale')):
      self.pose_mat = self.poseToPoseMat(pose['translation'],
                                            pose['rotation'], pose['scale'])
    else:
      raise ValueError("Unable to understand pose", pose)

    inverted = np.linalg.inv(self.pose_mat)
    rmat = inverted[0:3, 0:3]
    self._extrinsicsTVecs = inverted[0:3, 3:4]
    self._extrinsicsRVecs = cv2.Rodrigues(rmat)[0]

    pdict = self._poseMatToPose(self.pose_mat)
    self.translation = pdict['translation']
    self.quaternion_rotation = pdict['quaternion_rotation']
    self.euler_rotation = pdict['euler_rotation']
    self.scale = pdict['scale']

    if 'resolution' in pose and getattr(self, 'intrinsics', None) is not None:
      self.resolution = pose['resolution']
      self._calculateRegionOfView(self.resolution)
    return

  def cameraPointToWorldPoint(self, point):
    if point.is3D:
      npt = np.hstack((point.asNumpyCartesian, (1,)))
      return Point(np.matmul(self.pose_mat, npt)[:3])

    # creating a new array and reshaping it is far faster than np.append
    npt = np.reshape(np.array([point.asNumpyCartesian, (1, 1)]), -1)

    start = Point(np.matmul(self.pose_mat, np.array([0, 0, 0, 1]))[:3])
    end = Point(np.matmul(self.pose_mat, npt)[:3])

    pt = end - start
    if not pt.z == 0:
      # project detection to ground plane in world coordinate system
      scale = (0 - start.z) / pt.z
      pt = Point(pt.x * scale, pt.y * scale, pt.z * scale)
      pt = pt + start
    else:
      # no intersection exists between camera raycast and ground plane
      # preserve point in camera coordinate system
      pt = start
    return pt

  def transformObjectPoseInScene(self, obj, obj_T, obj_R):
    obj.translate(obj_T)
    obj.rotate(obj_R,center=(0,0,0))
    return obj

  def transformSceneToCameraCoordinates(self, obj, cam_T, cam_R):
    cam_pose_mat = np.vstack([
      np.hstack([cam_R,
                cam_T.reshape([3,1])]),
      np.array([0, 0, 0, 1])
      ])
    cam_extrinsics = np.linalg.inv(cam_pose_mat) # world 2 cam
    obj.transform(cam_extrinsics)
    return obj

# FIXME - projectToMap and projectBounds must be consolidated into a single method
  def projectToMap(self, obj_T, obj_R, map_obj, map_T, map_R):
    """!
    Project the object detection in 2D camera frame into 3D world coordinates
    @param    obj_T     object translation in camera csys
    @param    obj_R     object rotation in camera csys
    @param    map_obj   map as type o3d.geometry.TriangleMesh
    @param    map_T     map translation in scene csys
    @param    map_R     map rotation in scene csys

    @return   obj_T, obj_R translation and rotation of object projected to map
    """

    cam_T = self.translation.asNumpyCartesian
    cam_R = Rotation.from_quat(np.radians(self.quaternion_rotation)).as_matrix()
    map_obj = self.transformObjectPoseInScene(map_obj, map_T, map_R)
    map_obj = self.transformSceneToCameraCoordinates(map_obj, cam_T, cam_R)

    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(map_obj)
    rays = o3d.core.Tensor([[0, 0, 0, obj_T[0], obj_T[1], obj_T[2]]],dtype=o3d.core.Dtype.Float32)
    rcast = scene.cast_rays(rays)
    distance_ratio = rcast['t_hit'].numpy()[0]

    if not distance_ratio == np.inf:
      obj_R = Rotation.from_quat(obj_R).as_matrix()
      obj_T = (distance_ratio * np.array(obj_T)).tolist()
      v1 = (obj_R @ np.array([0, 0, 1]).reshape([3,1])).reshape([1,3]
        )[0] #object local z axis in camera csys
      v2 = rcast['primitive_normals'].numpy()[0] #surface normal vector in camera csys

      obj_R = Rotation.from_matrix(
        (rotationToTarget(v1,v2).as_matrix()) @ obj_R
        ).as_quat()
    return obj_T, obj_R

  def projectBounds(self, rect):
    """Project the bounding box from camera coordinate system to world coordinate system
    to determine the object location"""
    bl, br, far_l, far_r = self._mapCameraViewCornersToWorld(rect)

    ll1 = self.translation.distance(far_l)
    ll2 = bl.distance(far_l)
    al = math.atan2(self.translation.z, ll1)
    lh = math.sin(al) * ll2
    lw = bl.distance(br)
    # log.log("OBJECT SIZE %0.2fm x %0.2fm" % (lw, lh))
    # FIXME - return points in 3D
    bounds = Rectangle(origin=Point(bl.x, 0),
                       size=(lw, lh))
    shadow = (far_l, far_r, br, bl)

    basePoint = bl.midpoint(br)
    baseLen = Point(self.translation.x, self.translation.y, 0, polar=False).distance(basePoint)
    baseAngle = math.degrees(math.atan2(self.translation.z, baseLen))
    return bounds, shadow, baseAngle

  def projectWorldPointToCameraPixels(self, point):
    # FIXME - speed this up. cv2.projectPoints is very time consuming.
    # 10000 runs:
    # 15.508s    {projectPoints}
    pts, _ = cv2.projectPoints(point.asNumpyCartesian,
                               self._extrinsicsRVecs, self._extrinsicsTVecs,
                               self.intrinsics.intrinsics, self.intrinsics.distortion)
    return Point(np.squeeze(pts.reshape(-1, 2)))

  def projectEstimatedBoundsToCameraPixels(self, point, metricSize):
    left = Line(point, Point(metricSize.width / 2,
                             self.angle - 90,
                             0, polar=True), relative=True)
    top = Line(point, Point(metricSize.height, 0, 90, polar=True),
               relative=True)
    sensor_pt = self.projectWorldPointToCameraPixels(point)
    sensor_left = self.projectWorldPointToCameraPixels(left.end)
    sensor_top = self.projectWorldPointToCameraPixels(top.end)
    return Rectangle(origin=Point(sensor_left.x, sensor_top.y),
                     size=((sensor_pt.x - sensor_left.x) * 2, sensor_pt.y - sensor_top.y))

  def isBehindView(self, point):
    # FIXME - check if point is behind view
    raise NotImplementedError
    return True

  def _calculateRegionOfView(self, size):
    """Calculate the bounds of camera view on the map"""
    self.frameSize = size
    r = self.intrinsics.infer3DCoordsFrom2DDetection(Rectangle(origin=Point(0, 0), size=tuple(size)))
    ul, ur, bl, br = self._mapCameraViewCornersToWorld(r)

    # FIXME - having problems transforming upper right & upper left
    org2d = Point(self.translation.x, self.translation.y, 0, polar=False)
    a1 = Line(org2d, bl).angle
    a2 = Line(org2d, br).angle
    a3 = Line(org2d, ul).angle
    a4 = Line(org2d, ur).angle

    if abs(a1 - a3) > 0.05:
      log.debug("UPPER LEFT FAIL", ul, a1, a3, a1 - a3)
      l = org2d.distance(ul)
      ul = Line(org2d, Point(l, a1, 0, polar=True), relative=True).end
    if abs(a2 - a4) > 0.05:
      log.debug("UPPER RIGHT FAIL", ur, a2, a4, a2 - a4)
      l = org2d.distance(ur)
      ur = Line(org2d, Point(l, a2, 0, polar=True), relative=True).end

    if a1 < a2:
      a1 += 360
    self.angle = (a1 + a2) / 2 + 180
    self.angle %= 360.0
    self.regionOfView = Region(uuid=None, name=None, info=(ul.as2Dxy, ur.as2Dxy, br.as2Dxy, bl.as2Dxy))
    return

  def _mapCameraViewCornersToWorld(self, r):
    ul = self.cameraPointToWorldPoint(r.topLeft)
    ur = self.cameraPointToWorldPoint(r.topRight)
    bl = self.cameraPointToWorldPoint(r.bottomLeft)
    br = self.cameraPointToWorldPoint(r.bottomRight)
    return ul,ur,bl,br

  @staticmethod
  def _poseMatToPose(mat):
    rmat = mat[0:3, 0:3]
    cam_pos = mat[0:3, 3:4] #also T_mat
    rot = Rotation.from_matrix(rmat).as_euler('XYZ', degrees=True)

    scale = [mat[3, 3] * math.sqrt(rmat[0, 0]**2 + rmat[1, 0]**2 + rmat[2, 0]**2),
             mat[3, 3] * math.sqrt(rmat[0, 1]**2 + rmat[1, 1]**2 + rmat[2, 1]**2),
             mat[3, 3] * math.sqrt(rmat[0, 2]**2 + rmat[1, 2]**2 + rmat[2, 2]**2)]

    pose = {
      'translation': Point(cam_pos),
      'quaternion_rotation': Rotation.from_matrix(rmat).as_quat(), # TEST ME - calculate quaternion
      'euler_rotation': rot,
      'scale': scale
    }

    return pose

  @staticmethod
  def poseToPoseMat(translation, rotation, scale):
    if len(rotation) == 4:
      rmat = Rotation.from_quat(rotation).as_matrix()
    else:
      rmat = Rotation.from_euler('XYZ', rotation, degrees=True).as_matrix()
    tvecs = np.array(translation).reshape(3, -1)
    pose_mat = np.vstack((np.hstack((rmat, tvecs)), [0, 0, 0, 1]))
    diag_scale = np.diag(np.hstack([scale, [1]]))
    pose_mat = np.matmul(pose_mat, diag_scale)
    return pose_mat

  @staticmethod
  def arrayToDictionary(array, transformType):
    if transformType == "matrix":
      # This is a 4x3 or 4x4 transformation matrix
      return np.array(array).reshape(-1, 4)
    elif transformType == "euler":
      return {
        'translation': np.array(array[0:3]),
        'rotation': np.array(array[3:6]),
        'scale': np.array(array[6:9]),
      }
    elif transformType == "quaternion":
      return {
        'translation': np.array(array[0:3]),
        'rotation': np.array(array[3:7]),
        'scale': np.array(array[7:10]),
      }
    elif transformType == "3d-2d point correspondence":
      # Points will be in the format
      #   [c_y1, c_y1, c_x2, c_y2, ..., m_x1, m_y1, m_z1, m_x2, m_y2, m_z2, ...]
      # if the array is divisible by 5, otherwise it will have the legacy format
      #   [c_y1, c_y1, c_x2, c_y2, ..., m_x1, m_y1, m_x2, m_y2, ...]
      # where the z coordinate is assumed to be 0 and needs to be added
      if len(array) % 5 == 0:
        split_length = (len(array) // 5) * 2
        return {
          'camera points': np.array(array[:split_length]).reshape((split_length // 2, 2)),
          'map points': np.array(array[split_length:]).reshape((split_length // 2, 3)),
        }
      if len(array) % 4 == 0:
        split_length = len(array) // 2
        return {
          'camera points': np.array(array[:split_length]).reshape((split_length // 2, 2)),
          'map points': np.hstack((
            np.array(array[split_length:]).reshape((split_length // 2, 2)),
            np.zeros((split_length // 2, 1))
          )),
        }
      raise ValueError("Invalid array length for 3d-2d point correspondence")

    raise ValueError("Unknown transformType")

  @property
  def asDict(self):
    return {
      'translation': self.translation.asNumpyCartesian.tolist(),
      'rotation': self.euler_rotation.tolist(),
      'scale': self.scale,
    }

  def __repr__(self):
    return f"{self.__class__.__name__}: {{'translation': {self.translation}, 'rotation': {self.euler_rotation}, 'scale': {self.scale}}}"

def getPoseMatrix(sceneobj, rot_adjust=None):
  """! Extract the pose matrix of the scenescape object.

  @param sceneobj     Object in Scene
  @param rot_adjust   Rotation adjustment

  @return Pose Matrix
  """
  rotation = sceneobj.mesh_rotation
  if rot_adjust is not None:
    rotation = rotation - rot_adjust
  pose_mat = CameraPose.poseToPoseMat(sceneobj.mesh_translation, rotation, sceneobj.mesh_scale)

  return pose_mat

class PointCorrespondenceTransform(CameraPose):
  def __init__(self, pose, intrinsics):
    self.cameraPoints = np.array(pose['camera points'], dtype="float32")
    self.mapPoints = np.array(pose['map points'], dtype="float32")
    if self.mapPoints.shape[1] == 2:
      self.mapPoints = np.hstack((self.mapPoints, np.zeros((self.mapPoints.shape[0], 1))))
    self.intrinsics = intrinsics
    self.setResolution(pose['resolution'])
    return

  def calculatePoseMat(self):
    computation_method = cv2.SOLVEPNP_ITERATIVE
    # If the points are not coplanar, we need at least 6 points to calculate the pose
    # so we use an alternative computation method
    if (not self.arePointsCoplanar(self.mapPoints) and len(self.mapPoints < 6)):
      computation_method = cv2.SOLVEPNP_P3P

    _, rvec, tvec, = cv2.solvePnP(self.mapPoints, self.cameraPoints,
                                  self.intrinsics.intrinsics, self.intrinsics.distortion,
                                  flags=computation_method)
    rmat = cv2.Rodrigues(rvec)[0]
    pose_mat = np.linalg.inv(np.vstack((np.hstack((rmat, tvec)), [0, 0, 0, 1])))

    pdict = self._poseMatToPose(pose_mat)
    self.translation = pdict['translation']
    self.quaternion_rotation = pdict['quaternion_rotation']
    self.euler_rotation = pdict['euler_rotation']
    self.scale = pdict['scale']
    self.pose_mat = pose_mat
    return

  def setResolution(self, size):
    self.resolution = size
    self.calculatePoseMat()
    self._calculateRegionOfView(self.resolution)
    return

  def calculateDeterminant(self, points):
    p1, p2, p3, p4 = points

    v1 = np.array([p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]])
    v2 = np.array([p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]])
    v3 = np.array([p4[0] - p1[0], p4[1] - p1[1], p4[2] - p1[2]])

    return np.linalg.det(np.array([v1, v2, v3]))

  # This is necessary to check when we have 4 or 5 points since
  # SOLVEPNP_INTERATIVE needs 6 points if they are not coplanar
  def arePointsCoplanar(self, points):
    if len(points) == 5:
      for i in range(len(points)):
        subset = [points[j] for j in range(len(points)) if j != i]
        if abs(self.calculateDeterminant(subset)) > MAX_COPLANAR_DETERMINANT:
          return False
    elif len(points) == 4:
      if abs(self.calculateDeterminant(points)) > MAX_COPLANAR_DETERMINANT:
        return False
    return True

def applyChildTransform(region, cameraPose):
  """ Transforms the points in given region with the camera pose.
      of specified camera pose.

  @param    regions      list of regions
  @param    cameraPose   camera pose

  @return transformed region
  """
  if 'points' in region:
    region['points'] = list(map(lambda x:list(transform2DPoint(x, cameraPose)), region['points']))
  if 'x' in region and 'y' in region:
    region['x'], region['y'] = transform2DPoint((region['x'], region['y']), cameraPose)
  return region

def transform2DPoint(point, cameraPose):
  """ Transforms a 2D point with specified camera pose.

  @param    point      tuple of 2D point
  @param    cameraPose   camera pose

  @return transformed 2D point
  """
  translation = np.reshape(np.array([Point(point).asNumpyCartesian, (1, 1)]), -1)
  translation = np.matmul(cameraPose.pose_mat, translation)
  return translation[:2]

def convertToTransformMatrix(scene_pose_mat, rotation, translation):
  """!Transform cam to glb matrix to cam to world.
  @param  scene_pose_mat  Glb World Pose of glb.
  @param  rotation              Rotation values of an object in quaternion format.
  @param  translation           Translation values of an object.

  @return updated matrix in accordance with scenescape convention.
  """
  e_rot_0 = Rotation.from_quat(rotation).as_matrix()
  e_tr_0 = np.vstack([np.hstack([e_rot_0, np.zeros((3, 1))]),
                      np.array([0, 0, 0, 1])])
  cam_to_world = np.array([[1., 0., 0., translation[0]],
                          [0., 1., 0., translation[1]],
                          [0., 0., 1., translation[2]],
                          [0., 0., 0., 1.]])

  cam_to_world = cam_to_world @ e_tr_0
  cam_to_world = scene_pose_mat @ cam_to_world

  return cam_to_world


def normalize(vector):
  """Normalizes the input vector."""
  vector = vector.astype(float)
  magnitude = np.linalg.norm(vector)
  if magnitude == 0:
    return vector
  return vector / magnitude

def rotationToTarget(v1, v2):
  """Compute rotation (in quaternion) from vector v1 to v2"""
  quat = np.hstack([
           np.cross(v1, v2),
           np.array([
             (((np.linalg.norm(v1) ** 2) * (np.linalg.norm(v2) ** 2)) ** 0.5) + np.dot(v1, v2)
           ])
         ])
  if np.linalg.norm(quat) <= 1e-6:
    return None
  quat = normalize(quat)
  return Rotation.from_quat(quat)
