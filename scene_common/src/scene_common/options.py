#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common.mqtt import _Topic

APRILTAG = 'AprilTag'
MARKERLESS = 'Markerless'
MANUAL = 'Manual'

BOTTOM = 'bottom'
TOP = 'top'
NONE = 'none'

MATRIX = 'matrix'
EULER = 'euler'
QUATERNION = 'quaternion'
POINT_CORRESPONDENCE = '3d-2d point correspondence'

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
