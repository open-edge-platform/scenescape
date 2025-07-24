#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common import log
from fast_geometry import Point as cppPoint, Line as cppLine
from legacy_geometry.geometry import Point as pyPoint, Line as pyLine

def compareLines2D( cpp_ln : cppLine, py_ln : pyLine ):
  delta_angle = abs(cpp_ln.angle - py_ln.angle)
  delta_length = abs(cpp_ln.length - py_ln.length)
  delta_azimuth = abs(cpp_ln.azimuth - py_ln.azimuth)
  if delta_angle > 0.01 \
      or delta_length > 0.01 \
      or delta_azimuth > 0.01:
    print("Angle:", cpp_ln.angle, py_ln.angle)
    print("Length:", cpp_ln.length, py_ln.length)
    print("Azimuth:", cpp_ln.azimuth, py_ln.azimuth)
    return False
  return True

def compareLines3D( cpp_ln : cppLine, py_ln : pyLine ):
  if not compareLines2D(cpp_ln, py_ln):
    return False
  delta_inclination = abs(cpp_ln.inclination - py_ln.inclination)
  if delta_inclination > 0.01:
    print("Inclination:", cpp_ln.inclination, py_ln.inclination)
    return False
  return True

def testLines2D(start_range, stop_range, step):
  for x in range(start_range, stop_range, step):
    for y in range(start_range, stop_range, step):

      cpp_pt1 = cppPoint( x, y, polar=False )
      cpp_pt2 = cppPoint( y, x, polar=False )
      py_pt1 = pyPoint(x, y)
      py_pt2 = pyPoint(y, x)

      cpp_ln = cppLine(cpp_pt1, cpp_pt2)
      py_ln  = pyLine(py_pt1, py_pt2)

      if not compareLines2D(cpp_ln, py_ln):
        print("Failed comparing lines(2D) at", x, y)
        return False
  log.log("Lines (2D) ok")
  return True

def testLines3D(start_range, stop_range, step):
  for x in range(start_range, stop_range, step):
    for y in range(start_range, stop_range, step):

      cpp_pt1 = cppPoint( x, y, x+y, polar=False )
      cpp_pt2 = cppPoint( y, x, y, polar=False )
      py_pt1 = pyPoint(x, y, x+y)
      py_pt2 = pyPoint(y, x, y)

      cpp_ln = cppLine(cpp_pt1, cpp_pt2)
      py_ln  = pyLine(py_pt1, py_pt2)
      if not compareLines3D(cpp_ln, py_ln):
        print("Failed comparing lines(3D) at", x, y)
        return False
  log.log("Lines (3D) ok")
  return True

def testLines2DCross(start_range, stop_range, step):
  for x in range(start_range, stop_range, step):
    for y in range(start_range, stop_range, step):

      # m = dy / dx
      # y = mx + b -> b = y - mx

      if x != y:
        m = (x-y) / (y-x)
        b = x - m*y

        cpp_pt1 = cppPoint( x, y, polar=False )
        cpp_pt2 = cppPoint( y, x, polar=False )
        py_pt1 = pyPoint(x, y)
        py_pt2 = pyPoint(y, x)

        cpp_ln = cppLine(cpp_pt1, cpp_pt2)
        py_ln  = pyLine(py_pt1, py_pt2)

        cpp_pt3_i = cppPoint( (x+y)/2, ((x+y)/2)*m + b, polar=False )

        if b == 0:
          b = 0.5
        cpp_pt3_o = cppPoint( (x+y)/2, ((x+y)/2)*(m*1.1) + (b*1.1), polar=False )

        exp_y = cpp_ln.isPointOnLine(cpp_pt3_i)
        exp_n = cpp_ln.isPointOnLine(cpp_pt3_o)
        if exp_y != True:
          print("Failed at line v Point IN", x, y, cpp_pt3_i)
          return False
        if exp_n != False:
          print("Failed at line v Point OUT", x, y, cpp_pt3_o)
          return False
        if exp_y != py_ln.isPointOnLine(pyPoint(cpp_pt3_i.x, cpp_pt3_i.y)):
          print("Failed at line v Point IN vs legacy", x, y, cpp_pt3_i)
          return False
        if exp_n != py_ln.isPointOnLine(pyPoint(cpp_pt3_o.x, cpp_pt3_o.y)):
          print("Failed at line v Point OUT vs legacy", x, y, cpp_pt3_i)
          return False
  log.log("Lines cross points: ok")
  return True

def test():
  assert testLines2D(-50, 50, 2)
  assert testLines3D(-50, 50, 2)
  assert testLines2DCross(-50, 50, 2)

  return 0

if __name__ == '__main__':
  exit(test() or 0)
