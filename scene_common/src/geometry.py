# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import math

import numpy as np

from fast_geometry import Point, Line, Rectangle, Polygon, Size

DEFAULTZ = 0
ROI_Z_HEIGHT = 1.0

# Re-export modules from fast geometry as our own
__all__ = ['Point', 'Line', 'Rectangle', 'Size']

def isarray(a):
  return isinstance(a, (list, tuple, np.ndarray))

class Region:
  REGION_SCENE = 0
  REGION_POLY = 1
  REGION_CIRCLE = 2

  def __init__(self, uuid, name, info):
    self.uuid = uuid
    self.name = name
    self.area = None
    self.mesh = None
    self.objects = {}
    self.when = -1
    self.points_list = None
    self.polygon = None
    self.singleton_type = None
    self.updatePoints(info)
    self.updateSingletonType(info)
    self.updateVolumetricInfo(info)
    return

  def updatePoints(self, info):
    if (not self.hasPointsArray(info) and 'center' in info):
      pt = info['center']
      self.center = pt if isinstance(pt, Point) else Point(pt)

    if (self.hasPointsArray(info)) or ('area' in info and info['area'] == "poly"):
      self.area = Region.REGION_POLY
      self.points = []
      if not isarray(info):
        info = info['points']
      for pt in info:
        self.points.append(pt if isinstance(pt, Point) else Point(pt))
      self.findBoundingBox()
      self.points_list = [x.as2Dxy.asCartesianVector for x in self.points]
      if len(self.points_list) > 2:
        self.polygon = Polygon(self.points_list)
    elif 'area' in info and info['area'] == "circle":
      self.area = Region.REGION_CIRCLE
      self.radius = info['radius']
      # Rectangle is created using Point, Point constructor.
      self.boundingBox = Rectangle(self.center - (self.radius, self.radius),
                                   self.center + (self.radius, self.radius))
    elif 'area' in info and info['area'] == "scene":
      self.area = Region.REGION_SCENE
    else:
      raise ValueError("Unrecognized point data", info)
    return

  def hasPointsArray(self, info):
    return 'points' in info and isarray(info['points'])

  def updateSingletonType(self, info):
    if isinstance(info, dict):
      self.singleton_type = info.get('singleton_type', None)
    return

  def updateVolumetricInfo(self, info):
    if isinstance(info, dict):
      self.compute_intersection = info.get('volumetric', False)
      self.height = float(info.get('height', ROI_Z_HEIGHT))
      self.buffer_size = float(info.get('buffer_size', 0.0))
    return

  def findBoundingBox(self):
    tx, ty = self.points[0].as2Dxy.asCartesianVector
    bx = tx
    by = ty
    for point in self.points:
      tx = min(tx, point.x)
      ty = min(ty, point.y)
      bx = max(bx, point.x)
      by = max(by, point.y)
    self.boundingBox = Rectangle(origin=Point(tx, ty),
                                 opposite=Point(bx, by))
    return

  def isPointWithin(self, coord):
    if self.area == Region.REGION_SCENE:
      return True

    if not self.boundingBox.isPointWithin(coord):
      return False

    if self.area == Region.REGION_POLY:

      # if len(self.points) == 4:
      #   # Quadrilateral speed optimization
      #   diag1_x = abs(self.points[2].x - self.points[0].x)
      #   diag1_y = abs(self.points[2].y - self.points[0].y)
      #   diag2_x = abs(self.points[3].x - self.points[1].x)
      #   diag2_y = abs(self.points[3].y - self.points[1].y)
      #   dist_x = coord.x - self.points[0].x
      #   dist_y = coord.y - self.points[0].y
      #   area1 = diag1_x * diag1_x + diag1_y * diag1_y
      #   area2 = diag1_x * dist_x + diag1_y * dist_y
      #   area3 = diag2_x * diag2_x + diag2_y * diag2_y
      #   area4 = diag2_x * dist_x + diag2_y * dist_y
      #   return area1 >= area2 >= 0 and area3 >= area4 >= 0

      if len(self.points) > 2:
        if self.polygon is None:
          pts = [x.as2Dxy.asNumpyCartesian.flatten().tolist() for x in self.points]
          self.polygon = Polygon(pts)
        return self.polygon.isPointInside(coord.x, coord.y)

      return False

    dx = abs(coord.x - self.center.x)
    dy = abs(coord.y - self.center.y)

    if dx + dy <= self.radius:
      return True
    if dx*dx + dy*dy <= self.radius*self.radius:
      return True
    return False

  def serialize(self):
    data = {'points':[], 'title':self.name, 'uuid':self.uuid}
    if self.area == self.REGION_SCENE:
      data['area'] = "scene"
    elif self.area == self.REGION_CIRCLE:
      data['area'] = "circle"
      data['radius'] = self.radius
    elif self.area == self.REGION_POLY:
      data['area'] = "poly"
      data['points'] = self.coordinates
    if hasattr(self, "center"):
      data['x'], data['y'] = self.center.x, self.center.y
    return data

  @property
  def cv(self):
    return [x.cv for x in self.points]

  @property
  def coordinates(self):
    if hasattr(self, 'points'):
      return [np.array(x.asCartesianVector).tolist() for x in self.points]
    return None

  def __repr__(self):
    return "%s: person:%i vehicle:%i %s" % \
      (self.__class__.__name__,
       len(self.objects.get('person', [])), len(self.objects.get('vehicle', [])),
       self.coordinates)

class Tripwire(Region):
  def lineCrosses(self, line):
    for idx in range(len(self.points) - 1):
      pt1 = self.points[idx]
      pt2 = self.points[(idx + 1) % len(self.points)]
      segment = Line(pt1, pt2)
      isect = line.intersection(segment)
      if isect[0] and line.isPointOnLine(Point(isect[1])) \
          and segment.isPointOnLine(Point(isect[1])):
        direction = (line.x2 - segment.x1) * (segment.y2 - segment.y1) \
            - (line.y2 - segment.y1) * (segment.x2 - segment.x1)
        return int(math.copysign(1, direction))
    return 0

  def serialize(self):
    data = {
      'title': self.name,
      'points': self.coordinates,
      'uuid': self.uuid,
    }
    return data
