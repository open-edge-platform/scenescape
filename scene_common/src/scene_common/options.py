#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common.mqtt import _Topic

APRILTAG = 'AprilTag'
MARKERLESS = 'Markerless'
MANUAL = 'Manual'
# Strategy key for point-cloud based sensor registration. Used only for
# AutoCalibration strategy dispatch; not a Manager scene calibration choice.
POINTCLOUD = 'PointCloud'

BOTTOM = 'bottom'
TOP = 'top'
NONE = 'none'

MATRIX = 'matrix'
EULER = 'euler'
QUATERNION = 'quaternion'
POINT_CORRESPONDENCE = '3d-2d point correspondence'

# Pose provenance class (ADR 18). Behavioral bucket for UI follow and consumers.
POSE_CLASS_CALIBRATION = 'calibration'
POSE_CLASS_LIVE = 'live'

# Pose provenance origins (ADR 18). Extensible writer identity; phase-2 write ACL.
POSE_ORIGIN_MANAGER_REST = 'manager.rest'
POSE_ORIGIN_MANAGER_MESH = 'manager.mesh'
POSE_ORIGIN_MANAGER_IMPORT = 'manager.import'
POSE_ORIGIN_DETECTOR_EXTRINSICS = 'detector.extrinsics'
POSE_ORIGIN_EXTERNAL_SOURCE = 'external_source'
POSE_ORIGIN_UNKNOWN = 'unknown'

# Deprecated legacy pose_source strings; kept synced from provenance.class.
POSE_CONFIGURED = 'configured'
POSE_OBSERVATION = 'observation'


def make_pose_provenance(pose_class, origin, updated_at=None):
  """Build a pose_provenance dict for runtime camera state."""
  provenance = {
    'class': pose_class,
    'origin': origin,
  }
  if updated_at is not None:
    provenance['updated_at'] = updated_at
  return provenance


def provenance_from_camera_info(info):
  """Resolve calibration provenance from Manager/camera payload fields."""
  if not isinstance(info, dict):
    return make_pose_provenance(POSE_CLASS_CALIBRATION, POSE_ORIGIN_UNKNOWN)
  provenance = info.get('pose_provenance')
  if isinstance(provenance, dict) and provenance.get('class'):
    origin = provenance.get('origin') or POSE_ORIGIN_UNKNOWN
    return make_pose_provenance(
      provenance['class'], origin, provenance.get('updated_at'))
  origin = info.get('calibration_origin') or info.get('pose_origin')
  if origin:
    return make_pose_provenance(POSE_CLASS_CALIBRATION, origin)
  return make_pose_provenance(POSE_CLASS_CALIBRATION, POSE_ORIGIN_UNKNOWN)


def sync_legacy_pose_source(camera):
  """Keep camera.pose_source aligned with pose_provenance.class during migration."""
  provenance = getattr(camera, 'pose_provenance', None) or {}
  if provenance.get('class') == POSE_CLASS_LIVE:
    camera.pose_source = POSE_OBSERVATION
  else:
    camera.pose_source = POSE_CONFIGURED


def pose_is_live(camera):
  """True when runtime pose class is live (or legacy pose_source is observation)."""
  provenance = getattr(camera, 'pose_provenance', None) or {}
  if provenance.get('class') == POSE_CLASS_LIVE:
    return True
  return getattr(camera, 'pose_source', None) == POSE_OBSERVATION


ENVIRONMENTAL = 'environmental'
ATTRIBUTE = 'attribute'

SCENE = "scene"
CIRCLE = "circle"
POLY = "poly"

TYPE_1 = 1
TYPE_2 = 2

NO_ACCESS = 0
READ_ONLY = 1
WRITE_ONLY = 2
READ_AND_WRITE = 3
CAN_SUBSCRIBE = 4

BOOLEAN_CHOICES = (
    (True, 'Yes'),
    (False, 'No')
)

SHIFT_TYPE = (
    (TYPE_1, 'Type 1 (default)'),
    (TYPE_2, 'Type 2 (may work better for wide and short objects)'),
)

CALIBRATION_CHOICES = [
    (APRILTAG, 'AprilTag'),
    (MARKERLESS, 'Markerless'),
    (MANUAL, 'Manual')
  ]

CAM_FILTER_CHOICES = [
  (BOTTOM, 'Bottom'),
  (TOP, 'Top'),
  (NONE, 'None (default)')
]

CV_SUBSYSTEM_CHOICES = [
  ('AUTO', 'AUTO'),
  ('GPU', 'GPU'),
  ('CPU', 'CPU')
]

CAM_TRANSFORM_CHOICES = [
    (MATRIX, 'Matrix'),
    (EULER, 'Euler Angles'),
    (QUATERNION, 'Quaternion'),
    (POINT_CORRESPONDENCE, '3D-2D Point Correspondence')
  ]

CHILD_SCENE_TRANSFORM_CHOICES = [
    (MATRIX, 'Matrix'),
    (EULER, 'Euler Angles'),
    (QUATERNION, 'Quaternion')
  ]

SINGLETON_CHOICES = [
    (ENVIRONMENTAL, 'environmental'),
    (ATTRIBUTE, 'attribute')
  ]

AREA_CHOICES = [
    (SCENE, 'scene'),
    (CIRCLE, 'circle'),
    (POLY, 'poly')
  ]

ACCESS_CHOICES = [
        (NO_ACCESS, 'No access'),
        (READ_ONLY, 'Read only'),
        (WRITE_ONLY, 'Write only'),
        (READ_AND_WRITE, 'Read and Write'),
  ]

TOPIC_CHOICES = [(e.name, e.name) for e in _Topic]

MAP_TYPE_CHOICES = [
  ('map_upload', 'Map Upload'),
  ('geospatial_map', 'Geospatial Map'),
]

GEOSPATIAL_PROVIDERS = [('google', 'Google Maps'), ('mapbox', 'Mapbox')]
