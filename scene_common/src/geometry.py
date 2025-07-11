# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import math
import time

import open3d as o3d
import numpy as np
from scipy.spatial.transform import Rotation
VOLUMETRIC_AVAILABLE = True
try:
  import mapbox_earcut as earcut
except ImportError:
  print("Warning: volumetric intersection disabled.")
  VOLUMETRIC_AVAILABLE = False

BUFFER_AVAILABLE = True
try:
  from shapely import geometry
except ImportError:
  print("Warning: shapely module not found. Buffer operations are unavailable.")
  BUFFER_AVAILABLE = False

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

  def updatePoints(self, newPoints):
    if (not self.hasPointsArray(newPoints) and 'center' in newPoints):
      pt = newPoints['center']
      self.center = pt if isinstance(pt, Point) else Point(pt)

    if (self.hasPointsArray(newPoints)) or ('area' in newPoints and newPoints['area'] == "poly"):
      self.area = Region.REGION_POLY
      self.points = []
      if not isarray(newPoints):
        newPoints = newPoints['points']
      for pt in newPoints:
        self.points.append(pt if isinstance(pt, Point) else Point(pt))
      self.findBoundingBox()
      self.points_list = [x.as2Dxy.asCartesianVector for x in self.points]
      if len(self.points_list) > 2:
        self.polygon = Polygon(self.points_list)
    elif 'area' in newPoints and newPoints['area'] == "circle":
      self.area = Region.REGION_CIRCLE
      self.radius = newPoints['radius']
      # Rectangle is created using Point, Point constructor.
      self.boundingBox = Rectangle(self.center - (self.radius, self.radius),
                                   self.center + (self.radius, self.radius))
    elif 'area' in newPoints and newPoints['area'] == "scene":
      self.area = Region.REGION_SCENE
    else:
      raise ValueError("Unrecognized point data", newPoints)
    return

  def hasPointsArray(self, newPoints):
    return 'points' in newPoints and isarray(newPoints['points'])

  def updateSingletonType(self, info):
    if isinstance(info, dict):
      self.singleton_type = info.get('singleton_type', None)
    return

  def updateVolumetricInfo(self, info):
    if isinstance(info, dict):
      self.compute_intersection = info.get('volumetric', False)
      self.region_height = float(info.get('height', ROI_Z_HEIGHT))
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
  
  def createRegionMesh(self):
    """
    Create an extruded polygon mesh from region of interest polygon vertices
    """
    roi_pts = self.createBasePolygon()
    # Create base polygon points
    base_pts = np.array(roi_pts)
    n_points = len(base_pts)
    
    # 1. Triangulate the 2D polygon using Ear Clipping 👂
    # This algorithm correctly handles concave shapes by "clipping" triangular "ears".
    # The result is a list of vertex indices.
    triangle_indices = earcut.triangulate_float32(base_pts, np.array([n_points]))
    
    # Reshape the flat list of indices into a (n, 3) array of triangles.
    triangles = np.array(triangle_indices).reshape(-1, 3)

    # 2. Create vertices for the 3D mesh 🧊
    # Bottom vertices (z=0)
    bottom_vertices = np.hstack([base_pts, np.zeros((base_pts.shape[0], 1))])
    # Top vertices (z=height)
    top_vertices = np.hstack([base_pts, np.full((base_pts.shape[0], 1), self.region_height)])
    
    # Combine all vertices.
    vertices = np.vstack([bottom_vertices, top_vertices])

    # 3. Create triangular faces for the 3D mesh ✅
    num_vertices_2d = base_pts.shape[0]

    # Faces for the bottom and top caps come from our ear clipping result.
    bottom_triangles = triangles
    top_triangles = triangles + num_vertices_2d

    # Faces for the sides connect corresponding top and bottom vertices.
    side_triangles = []
    for i in range(num_vertices_2d):
        j = (i + 1) % num_vertices_2d  # Get the next vertex, wrapping around.
        side_triangles.append([i, j, i + num_vertices_2d])
        side_triangles.append([j, j + num_vertices_2d, i + num_vertices_2d])

    # Combine all the triangle sets.
    all_triangles = np.vstack([bottom_triangles, top_triangles, np.array(side_triangles)])

    # 4. Create the Open3D TriangleMesh
    self.mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices),
        o3d.utility.Vector3iVector(all_triangles)
    )

    # Compute normals for correct shading and lighting.
    self.mesh.compute_vertex_normals()
    return

  def createBasePolygon(self):
    mitre_inflated = None
    if BUFFER_AVAILABLE:
      base_polygon = geometry.Polygon([(pt.x, pt.y) for pt in self.points])
      mitre_inflated = base_polygon.buffer(self.buffer_size, join_style=2)

    roi_pts = None
  # Extract coordinates from inflated polygon
  # Handle both simple and complex polygons during inflation
    if mitre_inflated is not None:
    # For complex polygons with holes
      if hasattr(mitre_inflated, 'geom_type') and mitre_inflated.geom_type == 'MultiPolygon':
      # Take the largest polygon from the multipolygon result
        largest_poly = max(mitre_inflated.geoms, key=lambda g: g.area)
        inflated_coords = list(largest_poly.exterior.coords)
        roi_pts = [[x, y] for x, y in inflated_coords]
      elif hasattr(mitre_inflated, 'exterior'):
      # Single polygon result
        inflated_coords = list(mitre_inflated.exterior.coords)
        roi_pts = [[x, y] for x, y in inflated_coords]
    else:
      roi_pts = [[pt.x, pt.y] for pt in self.points]
    return roi_pts
    
  def createObjectMesh(self, obj):
    # populate object
    if not (hasattr(obj, 'size') and isarray(obj.size) and all(isinstance(s, (int, float)) for s in obj.size)):
      raise ValueError("Object must have a valid 'size' attribute (list or array of numbers)")
    
    if not (hasattr(obj, 'rotation') and isarray(obj.rotation) and len(obj.rotation) == 4):
      raise ValueError("Object must have a valid 'rotation' attribute (quaternion)")
    
    if not (hasattr(obj, 'sceneLoc') and hasattr(obj.sceneLoc, 'asNumpyCartesian')):
      raise ValueError("Object must have a valid 'sceneLoc' attribute with 'asNumpyCartesian' method")
    
    # Create a basic box mesh
    mesh = o3d.geometry.TriangleMesh.create_box(
      obj.size[0],
      obj.size[1],
      obj.size[2]
    )
    
    # Center the box at origin
    mesh = mesh.translate(np.array([
      -obj.size[0]/2,
      -obj.size[1]/2,
      0
    ]))
    
    # Rotate the box based on quaternion
    try:
      rotation_matrix = Rotation.from_quat(np.array(obj.rotation)).as_matrix()
      mesh = mesh.rotate(
        rotation_matrix,
        center=np.zeros(3)
      )
    except Exception as e:
      raise ValueError(f"Failed to apply rotation: {e}")
    
    # Translate to final position
    try:
      mesh = mesh.translate(obj.sceneLoc.asNumpyCartesian)
    except Exception as e:
      raise ValueError(f"Failed to translate mesh to sceneLoc: {e}")
    obj.mesh = mesh.compute_vertex_normals()
    return

  def is_intersecting(self, obj):
    if not self.compute_intersection or not VOLUMETRIC_AVAILABLE:
      return False

    if self.mesh == None:
      self.createRegionMesh()

    try:
      self.createObjectMesh(obj)
    except ValueError as e:
      print(f"Error creating object mesh for intersection check: {e}")
      return False

    intersecting = obj.mesh.is_intersecting(self.mesh)
    return intersecting


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
