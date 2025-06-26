# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

# Wrappers to do drawing and automatically scale borders/font size/radius up to fit image size

import cv2

_SCL_NORMAL = 640

def scl_line(image, start_point, end_point, color, thickness):
  scale = image.shape[1] / _SCL_NORMAL
  return cv2.line(image, start_point, end_point, color, int(thickness * scale))

def scl_rect(image, start_point, end_point, color, thickness):
  scale = image.shape[1] / _SCL_NORMAL
  return cv2.rectangle(image, start_point, end_point, color, int(thickness * scale))

def scl_circle(image, center, radius, color, thickness):
  scale = image.shape[1] / _SCL_NORMAL
  return cv2.circle(image, center, int(radius * scale), color, int(thickness * scale))

def scl_polylines(image, points, closed, color, thickness):
  scale = image.shape[1] / _SCL_NORMAL
  return cv2.polylines(image, points, closed, color, int(thickness * scale))

# Super fancy text drawing that allows specifying point relative location
def scl_text_size(image, label, point, point_rel, font, fsize, thickness):
  scale = image.shape[1] / _SCL_NORMAL
  size, baseline = cv2.getTextSize(label, font, fsize * scale, int(thickness * scale))
  offset_x = ((point_rel[0] + 1) / 2) * size[0]
  offset_y = ((point_rel[1] + 1) / 2) * size[1]
  origin = (int(point[0] - offset_x), int(point[1] + offset_y))
  return size, origin, scale

def scl_text(image, label, point, point_rel, font, fsize, color, thickness):
  size, origin, scale = scl_text_size(image, label, point, point_rel, font, fsize, thickness)
  cv2.putText(image, label, origin, font, fsize * scale, color, int(thickness * scale))
  return size
