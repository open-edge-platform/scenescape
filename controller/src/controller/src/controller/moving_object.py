# Copyright (C) 2021-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import base64
import datetime
import struct
import warnings
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List

import cv2
import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation

from scene_common.geometry import DEFAULTZ, Line, Point, Rectangle
from scene_common.options import TYPE_1, TYPE_2
from scene_common.transform import normalize, rotationToTarget

warnings.simplefilter('ignore', np.RankWarning)

APRILTAG_HOVER_DISTANCE = 0.5
DEFAULT_EDGE_LENGTH = 1.0
DEFAULT_TRACKING_RADIUS = 2.0
LOCATION_LIMIT = 20
SPEED_THRESHOLD = 0.1

@dataclass
class ChainData:
  regions: Dict
  publishedLocations: List[Point]
  sensors: Dict

class Chronoloc:
  def __init__(self, point: Point, when: datetime, bounds: Rectangle):
    if not point.is3D:
      point = Point(point.x, point.y, DEFAULTZ)
    self.point = point
    self.when = when
    self.bounds = bounds
    return

class Vector:
  def __init__(self, camera, point, when):
    if not point.is3D:
      point = Point(point.x, point.y, DEFAULTZ)
    self.camera = camera
    self.point = point
    self.last_seen = when
    return

  def __repr__(self):
    origin = None
    if hasattr(self.camera, 'pose'):
      origin = str(self.camera.pose.translation.log)
    return "Vector: %s %s %s" % \
      (origin, str(self.point.log), self.last_seen)

class MovingObject:
  ## Fields that are specific to a single detection:
  # 'tracking_radius', 'camera', 'boundingBox', 'boundingBoxPixels',
  # 'confidence', 'oid', 'reidVector', 'visibility'

  ## Fields that really are shared across the chain:
  # 'gid', 'frameCount', 'velocity', 'intersected',
  # 'first_seen', 'category'

  gid_counter = 0
  gid_lock = Lock()

  def __init__(self, info, when, camera):
    self.chain_data = None
    self.size = None
    self.tracking_radius = DEFAULT_TRACKING_RADIUS
    self.shift_type = TYPE_1
    self.project_to_map = False
    self.map_triangle_mesh = None
    self.map_translation = None
    self.map_rotation = None
    self.rotation_from_velocity = False

    self.first_seen = when
    self.last_seen = None
    self.camera = camera
    self.info = info.copy()

    self.category = self.info.get('category', 'object')
    self.boundingBox = None
    if 'bounding_box_px' in self.info:
      self.boundingBoxPixels = Rectangle(self.info['bounding_box_px'])
      self.info.pop('bounding_box_px')
      if not 'bounding_box' in self.info:
        agnostic = self.camera.pose.intrinsics.infer3DCoordsFrom2DDetection(self.boundingBoxPixels)
        self.boundingBox = agnostic
    if 'bounding_box' in self.info:
      self.boundingBox = Rectangle(self.info['bounding_box'])
      self.info.pop('bounding_box')
    self.confidence = self.info['confidence'] if 'confidence' in self.info else None
    self.oid = self.info['id']
    self.info.pop('id')
    self.gid = None
    self.frameCount = 1
    self.velocity = None
    self.location = None
    self.rotation = None
    self.intersected = False
    self.reidVector = None
    reid = self.info.get('reid', None)
    if reid is not None:
      self._decodeReIDVector(reid)
    return

  def _decodeReIDVector(self, reid):
    try:
      vector = base64.b64decode(reid)
      self.reidVector = np.array(struct.unpack("256f", vector)).reshape(1, -1)
      self.info.pop('reid')
    except TypeError:
      if type(reid) == list:
        self.reidVector = reid
    return

  def setGID(self, gid):
    self.chain_data = ChainData(regions={}, publishedLocations=[], sensors={})
    self.gid = gid
    self.first_seen = self.when
    return

  def setPrevious(self, otherObj):
    # log.debug("MATCHED", self.__class__.__name__,
    #     "id=%i/%i:%i" % (otherObj.gid, otherObj.oid, self.oid),
    #     otherObj.sceneLoc, self.sceneLoc)
    self.location = [self.location[0]] + otherObj.location[:LOCATION_LIMIT - 1]
    self.chain_data = otherObj.chain_data

    # FIXME - should these fields be part of chain_data?
    self.gid = otherObj.gid
    self.first_seen = otherObj.first_seen
    self.frameCount = otherObj.frameCount + 1

    del self.chain_data.publishedLocations[LOCATION_LIMIT:]

    return

  def inferRotationFromVelocity(self):
    if self.rotation_from_velocity and self.velocity:
      speed = np.linalg.norm([self.velocity.x, self.velocity.y, self.velocity.z])
      if speed > SPEED_THRESHOLD:
        velocity = np.array([self.velocity.x, self.velocity.y, self.velocity.z])
        velocity = normalize(velocity)
        direction = np.array([1, 0, 0])
        self.rotation = rotationToTarget(direction, velocity).as_quat().tolist()
    elif self.rotation is None:
      self.rotation = np.array([0, 0, 0, 1]).tolist()
    return

  @property
  def camLoc(self):
    """Object location in camera coordinate system"""
    bounds = self.boundingBox
    if self.shift_type == TYPE_2:
      if not hasattr(self, 'baseAngle'):
        self._projectBounds()
      return Point(bounds.x + bounds.width / 2,
                 bounds.y + bounds.height - (bounds.height / 2) * (self.baseAngle / 90))
    else:
      pt = Point(bounds.x + bounds.width / 2, bounds.y2)
      if bounds.origin.is3D:
        pt = Point(pt.x, pt.y, bounds.origin.z)
    return pt

  def mapObjectDetectionToWorld(self, info, when, camera):
    """Maps detected object pose to world coordinate system"""
    if info is not None and 'size' in info:
      self.size = info['size']
    if info is not None and 'translation' in info:
      self.orig_point = Point(info['translation'])
      if camera and hasattr(camera, 'pose'):
        if 'rotation' in info:
          if self.project_to_map:
            info['translation'], info['rotation'] = camera.pose.projectToMap(info['translation'],
                                                                        info['rotation'],
                                                                        self.map_triangle_mesh.clone(),
                                                                        o3d.core.Tensor(self.map_translation, dtype=o3d.core.Dtype.Float32),
                                                                        o3d.geometry.get_rotation_matrix_from_xyz(self.map_rotation))
          rotation_as_matrix = Rotation.from_quat(np.array(info['rotation'])).as_matrix()
          info['rotation'] = list(Rotation.from_matrix(np.matmul(
                                      camera.pose.pose_mat[:3,:3],
                                      rotation_as_matrix)).as_quat())
          self.rotation = info['rotation']
        self.orig_point = camera.pose.cameraPointToWorldPoint(Point(info['translation']))
    else:
      if camera and hasattr(camera, 'pose'):
        self.orig_point = camera.pose.cameraPointToWorldPoint(self.camLoc)
        if not self.camLoc.is3D:
          line1 = Line(camera.pose.translation, self.orig_point)
          line2 = Line(self.orig_point, Point(np.mean([self.size[0], self.size[1]]) / 2, line1.angle, 0, polar=True), relative=True)
          self.orig_point = line2.end
    self.location = [Chronoloc(self.orig_point, when, self.boundingBox)]
    self.vectors = [Vector(camera, self.orig_point, when)]
    return

  @property
  def sceneLoc(self):
    """Object location in world coordinate system"""
    if self.intersected:
      return self.adjusted[1]
    if not hasattr(self, 'location') or not self.location:
      self._projectBounds()
      self.mapObjectDetectionToWorld(self.info, self.first_seen, self.camera)
    return self.location[0].point

  def _projectBounds(self):
    if hasattr(self.camera, "pose") and self.boundingBox:
      self.bbMeters, self.bbShadow, self.baseAngle = \
        self.camera.pose.projectBounds(self.boundingBox)
      if self.size is None:
        self.size = [self.bbMeters.width, self.bbMeters.width, self.bbMeters.height]
    return

  @property
  def when(self):
    return self.location[0].when

  def __repr__(self):
    return "%s: %s/%s %s %s vectors: %s" % \
      (self.__class__.__name__,
       str(self.gid), self.oid,
       str(self.sceneLoc.log),
       str(self.location[1].point.log) if len(self.location) > 1 else None,
       str(self.vectors))

  @classmethod
  def createSubclass(cls, subclassName, methods=None, additionalAttributes=None):
    """ Dynamically creates a subclass with specified methods and additional attributes.
    @param    subclassName              The name of the new subclass.
    @param    methods                   A dictionary of methods to add to the subclass.
    @param    additionalAttributes     A dictionary of additional attributes for the subclass.
    @returns  class                     The dynamically created subclass.
    """

    classDict = {'baseClass': cls}
    classDict.update('')
    if methods:
      classDict.update(methods)

    newClass = type(subclassName, (cls,), classDict)
    def custom_init(self, *args, **kwargs):
      cls.__init__(self, *args, **kwargs)
      if additionalAttributes:
        classDict.update(additionalAttributes)

    setattr(newClass, '__init__', custom_init)
    return newClass

  ### Below section is for methods that support native tracker or tracker debugger
  def displayIntersections(self, img, ms, pad):
    # for o1 in range(len(self.vectors) - 1):
    #   org1 = self.vectors[o1]
    #   pt = org1.point
    #   l1 = (org1.camera.pose.translation, pt)
    #   for o2 in range(o1 + 1, len(self.vectors)):
    #     org2 = self.vectors[o2]
    #     pt = org2.point
    #     l2 = (org2.camera.pose.translation, pt)
    #     point = scenescape.intPoint(scenescape.lineIntersection(l1, l2))
    #     cv2.line(img, (point[0] - 5, point[1]), (point[0] + 5, point[1]), (128,128,128), 2)
    #     cv2.line(img, (point[0], point[1] - 5), (point[0], point[1] + 5), (128,128,128), 2)
    #     label = "%i" % (self.gid)
    #     cv2.putText(img, label, point, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 3)
    #     cv2.putText(img, label, point, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    for org in self.vectors:
      pt1 = ms(pad, org.camera.pose.translation)
      pt2 = ms(pad, org.point)
      point = Point((pt1.x + (pt2.x - pt1.x) / 2, pt1.y + (pt2.y - pt1.y) / 2))
      label = "%i %0.3f,%0.3f" % (self.gid, org.point.x, org.point.y)
      cv2.putText(img, label, point.cv, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 3)
      cv2.putText(img, label, point.cv, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    return

  def dump(self):
    dd = {
      'category': self.category,
      'bounding_box': self.boundingBox.asDict,
      'gid': self.gid,
      'frame_count': self.frameCount,
      'reid': self.reidVector,
      'first_seen': self.first_seen,
      'location': [{'point': (v.point.x, v.point.y, v.point.z),
                    'timestamp': v.when,
                    'bounding_box': v.bounds.asDict} for v in self.location],
      'vectors': [{'camera': v.camera.cameraID,
                   'point': (v.point.x, v.point.y, v.point.z),
                   'timestamp': v.last_seen} for v in self.vectors],
      'intersected': self.intersected,
      'scene_loc': self.sceneLoc.asNumpyCartesian.tolist(),
    }
    if 'reid' in dd and isinstance(dd['reid'], np.ndarray):
      vector = dd['reid'].flatten().tolist()
      vector = struct.pack("256f", *vector)
      vector = base64.b64encode(vector).decode('utf-8')
      dd['reid'] = vector
    if self.intersected:
      dd['adjusted'] = {'gid': self.adjusted[0],
                        'point': (self.adjusted[1].x, self.adjusted[1].y, self.adjusted[1].z)}
    return dd

  def load(self, info, scene):
    self.category = info['category']
    self.boundingBox = Rectangle(info['bounding_box'])
    self.gid = info['gid']
    self.frameCount = info['frame_count']
    self.reidVector = info['reid']
    if self.reidVector is not None:
      vector = base64.b64decode(self.reidVector)
      self.reidVector = np.array(struct.unpack("256f", vector)).reshape(1, -1)
    self.first_seen = info['first_seen']
    self.location = [Chronoloc(Point(v['point']), v['timestamp'], Rectangle(v['bounding_box']))
                     for v in info['location']]
    self.vectors = [Vector(scene.cameras[v['camera']], Point(v['point']), v['timestamp'])
                    for v in info['vectors']]
    if 'intersected' in info:
      self.intersected = info['intersected']
      if self.intersected:
        self.adjusted = [info['adjusted']['gid'], Point(info['adjusted']['point'])]
        if not self.adjusted[1].is3D:
          self.adjusted[1] = Point(self.adjusted[1].x, self.adjusted[1].y, DEFAULTZ)
    return

class ATagObject(MovingObject):
  def __init__(self, info, when, sensor):
    super().__init__(info, when, sensor)

    self.tag_id = "%s-%s-%s" % (info['category'], info['tag_family'], info['tag_id'])
    return

  def mapObjectDetectionToWorld(self, info, when, sensor):
    super().mapObjectDetectionToWorld(info, when, sensor)

    if not hasattr(sensor, 'pose'):
      return

    # Do the math to make the tag hover above the floor at hover_dist
    hover_dist = APRILTAG_HOVER_DISTANCE # Tag is this many meters above the floor

    # Scale the triangle down to a Z of hover_dist to find point above floor
    pt = sensor.pose.translation - self.orig_point
    if not pt.z == 0:
      pt = Point(hover_dist * pt.x / pt.z, hover_dist * pt.y / pt.z, hover_dist * pt.z / pt.z)
      pt = pt + self.orig_point
      self.orig_point = pt

    bbox = getattr(self, "boundingBox", None)
    self.location = [Chronoloc(self.orig_point, when, bbox)]
    self.vectors = [Vector(sensor, self.orig_point, when)]
    return

  def __repr__(self):
    rep = super().__repr__()
    rep += " %s" % (self.tag_id)
    return rep
