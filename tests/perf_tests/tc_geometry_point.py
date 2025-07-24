#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common import log
from fast_geometry import Point as cppPoint
from legacy_geometry.geometry import Point as pyPoint

def comparePointPolarAttributes2D(cpp_pt : cppPoint, py_pt : pyPoint):
  delta_rad = abs(cpp_pt.radius - py_pt.radius)
  delta_az = abs(cpp_pt.azimuth - py_pt.azimuth)
  if delta_rad > 0.01 \
      or delta_az > 0.01:
    print("Mismatch in Polar math")
    print("Radius", cpp_pt.radius, "vs", py_pt.radius)
    print("Length", cpp_pt.length, "vs", py_pt.length)
    print("Azimuth", cpp_pt.azimuth, "vs", py_pt.azimuth)
    return False
  return True

def comparePointPolarAttributes3D(cpp_pt : cppPoint, py_pt : pyPoint):
  if not comparePointPolarAttributes2D(cpp_pt, py_pt):
    return False
  delta_inc = abs(cpp_pt.inclination - py_pt.inclination)
  if delta_inc > 0.01:
    print("Mismatch in Polar math")
    print("Inclination", cpp_pt.inclination, "vs", py_pt.inclination)
    return False
  return True

def comparePointCartesianAttributes2D(cpp_pt : cppPoint, py_pt : pyPoint):
  delta_rad = abs(cpp_pt.radius - py_pt.radius)
  delta_x = abs(cpp_pt.x - py_pt.x)
  delta_y = abs(cpp_pt.y - py_pt.y)
  if delta_rad > 0.01 \
      or delta_x > 0.01 \
      or delta_y > 0.01:
    print("Mismatch in Cartesian math")
    print("Rad", cpp_pt.radius, "vs", py_pt.radius)
    print("X", cpp_pt.x, "vs", py_pt.x)
    print("Y", cpp_pt.y, "vs", py_pt.y)
    return False
  return True

def comparePointCartesianAttributes3D(cpp_pt : cppPoint, py_pt : pyPoint):
  if not comparePointCartesianAttributes2D(cpp_pt, py_pt):
    return False
  delta_z = abs(cpp_pt.z - py_pt.z)
  if delta_z > 0.01:
    print("Mismatch in Cartesian math")
    print("Z", cpp_pt.z, "vs", py_pt.z)
    return False
  return True

def testPointsPolarAttributes3D(start_range, stop_range, step):
  for x in range(start_range, stop_range, step):
    for y in range(start_range, stop_range, step):
      for z in range(start_range, stop_range, step):
        cpp_pt = cppPoint(x, y, z, polar=False)
        py_pt  = pyPoint(x, y, z)

        if not comparePointPolarAttributes3D(cpp_pt, py_pt):
          print("Failed in Polar Attributes for 3D points in", x, y, z)
          return False
  log.log("Cartesian to Polar (3D) ok")
  return True

def testPointsPolarAttributes2D(start_range, stop_range, step):
  for x in range(start_range, stop_range, step):
    for y in range(start_range, stop_range, step):
      cpp_pt = cppPoint(x, y, polar=False)
      py_pt  = pyPoint(x, y)

      if not comparePointPolarAttributes2D(cpp_pt, py_pt):
        print("Failed in Polar Attributes for 2D points in", x, y)
        return False
  log.log("Cartesian to Polar (2D) ok")
  return True

def testPointsCartesianAttributes3D(start_range, stop_range, step):
  for r_radius in range(1, 100, 1):
    # This simply generates radius values from 0.1 to 10.1
    radius = float(r_radius - 1) / 10.0 + 0.1
    for az in range(start_range, stop_range, step):
      for inc in range(start_range, stop_range, step):
        cpp_pt = cppPoint(radius, az, inc, polar=True)
        py_pt  = pyPoint(radius, az, inc, polar=True)

        if not comparePointCartesianAttributes3D(cpp_pt, py_pt):
          print("Failed in Cartesian Attributes for 3D points in", radius, az, inc)
          return False

        cpp_pt = cpp_pt.asCartesian
        py_pt = py_pt.asCartesian
        if not comparePointPolarAttributes3D(cpp_pt, py_pt):
          print("Failed in Polar->Cartesian->Polar Attributes for points in", radius, az, inc)
          return False

        cpp_ptxy = cpp_pt.as2Dxy
        cpp_ptxz = cpp_pt.as2Dxz
        cpp_ptyz = cpp_pt.as2Dyz

        if cpp_ptxy.x != cpp_pt.x or cpp_ptxy.y != cpp_pt.y:
          print("Failed ptxy:", cpp_ptxy, "vs orig", cpp_pt)
          return False
        if cpp_ptyz.x != cpp_pt.y or cpp_ptyz.y != cpp_pt.z:
          print("Failed ptyz:", cpp_ptyz, "vs orig", cpp_pt)
          return False
  log.log("Polar to Cartesian (3D) ok")
  return True

def testPointsCartesianAttributes2D(start_range, stop_range, step):
  for r_radius in range(1, 100, 1):
    # This simply generates radius values from 0.1 to 10.1
    radius = float(r_radius - 1) / 10.0 + 0.1
    for az in range(start_range, stop_range, step):
      cpp_pt = cppPoint(radius, az, polar=True)
      py_pt  = pyPoint(radius, az, polar=True)

      if not comparePointCartesianAttributes2D(cpp_pt, py_pt):
        print("Failed in Cartesian Attributes for 2D points in", radius, az)
        return False
  log.log("Polar to Cartesian (2D) ok")
  return True

def test():
  assert testPointsPolarAttributes2D(-50, 50, 2)
  assert testPointsPolarAttributes3D(-50, 50, 2)
  assert testPointsCartesianAttributes2D(-50, 50, 2)
  assert testPointsCartesianAttributes3D(-50, 50, 2)

  return 0

if __name__ == '__main__':
  exit(test() or 0)
