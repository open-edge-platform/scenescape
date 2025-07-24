# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import math
import numpy as np
import operator

DEFAULTZ = 0

class PolarArithmeticError(ArithmeticError):
  pass

class Point:
  def __init__(self, a=None, b=None, c=None, polar=False,
               x=None, y=None, z=None,
               length=None, angle=None,
               radius=None, azimuth=None, inclination=None):
    """Represents a 2D or 3D polar or cartesian coordinate. Is able to do
    conversions between types and simple operations like comparison
    and addition.
    Arguments can be a tuple/list/ndarray which is expected to be in
    the correct order. Or arguments can be coordinates specified individually.
    Examples:
      Point([1, 2, 3]) - creates a 3D coordinate of x=1, y=2, z=3
      Point(5, 7, 11) - creates a 3D coordinate of x=5, y=7, z=11
      Point(4, 6) - creates a 2D coordinate of x=4, y=6
      Point(13, 17, 29, polar=True) - creates a 3D polar coordinate of
        radius=13, azimuth=17, inclination=29
      Point(radius=13, azimuth=17, inclination=29) - creates a 3D polar
        coordinate of radius=13, azimuth=17, inclination=29
    """

    if a is None and not isinstance(polar, bool):
      a = polar
      polar = True
    if x is not None:
      a = x
    if y is not None:
      b = y
    if z is not None:
      c = z
    if length is not None:
      a = length
      polar = True
    if angle is not None:
      b = angle
      polar = True
    if radius is not None:
      a = radius
      polar = True
    if azimuth is not None:
      b = azimuth
      polar = True
    if inclination is not None:
      c = inclination
      polar = True

    if a is None:
      raise ValueError("No coordinates")
    self.polar = polar
    if isinstance(a, dict):
      if 'length' in a:
        self._point = (a['length'], a['angle'], None)
        polar = True
      elif 'radius' in a:
        self._point = (a['radius'], a['azimuth'], a['inclination'])
        polar = True
      elif 'z' in a:
        self._point = (a['x'], a['y'], a['z'])
      else:
        self._point = (a['x'], a['y'], None)
    elif isinstance(a, (list, tuple)):
      if None in a:
        raise ValueError("Passed arguments do not make a coordinate", type(a), a)
      self._point = tuple(a)
      if len(self._point) < 3:
        self._point = tuple((list(self._point) + [None] * 3)[:3])
    elif isinstance(a, np.ndarray):
      self._point = tuple(a.flatten().tolist())
      if len(self._point) < 3:
        self._point = tuple((list(self._point) + [None] * 3)[:3])
    elif isinstance(a, complex):
      self._point = (a.real, a.imag, None)
    elif b is not None:
      self._point = (a, b, c)
    else:
      raise ValueError("Passed arguments do not make a coordinate", type(a), a)
    return

  def midpoint(self, other):
    if self.is3D != other.is3D:
      raise TypeError("Cannot mix 2D and 3D points")
    if self.is3D:
      return self.__class__(self.x + (other.x - self.x) / 2, self.y + (other.y - self.y) / 2,
                   self.z + (other.z - self.z) / 2)
    return self.__class__(self.x + (other.x - self.x) / 2, self.y + (other.y - self.y) / 2)

  def withinRadius(self, pt, radius):
    if self.is3D:
      raise TypeError("Not a 2D point")
    if Line(self, pt).length <= radius:
      return True
    return False

  @property
  def x(self):
    if not self.polar:
      return self._point[0]
    return self.radius * math.cos(math.radians(self.angle))

  @property
  def y(self):
    if not self.polar:
      return self._point[1]

    if self.is3D:
      return self.radius * math.cos(math.radians(self.inclination)) \
        * math.sin(math.radians(self.azimuth))
    return self.radius * math.sin(math.radians(self.angle))

  @property
  def z(self):
    if not self.is3D:
      raise TypeError("Cannot get Z from 2D point")
    if self.polar:
      return self.radius * math.sin(math.radians(self.inclination)) \
        * math.cos(math.radians(self.azimuth))
    return self._point[2]

  @property
  def length(self):
    return self.radius

  @property
  def angle(self):
    return self.azimuth

  @property
  def radius(self):
    if self.polar:
      return self._point[0]

    squared = self._point[0] ** 2 + self._point[1] ** 2
    if self.is3D:
      squared += self._point[2] ** 2
    return math.sqrt(squared)

  @property
  def azimuth(self):
    if self.polar:
      return self._point[1]

    angle = math.degrees(math.atan2(self._point[1], self._point[0]))
    angle %= 360.0
    return angle

  @property
  def inclination(self):
    if not self.is3D:
      raise TypeError("Cannot get inclination from 2D point")
    if self.polar:
      return self._point[2]

    if self.is3D:
      squared = self._point[0] ** 2 + self._point[1] ** 2
      angle = math.degrees(math.atan2(math.sqrt(squared), self._point[2]))
    else:
      angle = math.degrees(math.atan2(self._point[0], self._point[1]))
    angle = 90 - angle
    angle %= 360.0
    return angle

  @property
  def cv(self):
    if self.is3D:
      raise TypeError("Cannot get cv from 3D point")
    return (int(self.x), int(self.y))

  @property
  def is3D(self):
    return self._point[2] is not None

  @property
  def asCartesian(self):
    if not self.polar:
      return self

    if self.is3D:
      return self.__class__(self.x, self.y, self.z)
    return self.__class__(self.x, self.y)

  @property
  def asPolar(self):
    if self.polar:
      return self

    if self.is3D:
      return self.__class__(self.radius, self.azimuth, self.inclination)
    return self.__class__(self.length, self.angle)

  @property
  def asNumpyCartesian(self):
    if not hasattr(self, '_numpyCartesian'):
      if not self.polar:
        coords = 2
        if self.is3D:
          coords += 1
        self._numpyCartesian = np.float64(self._point[:coords])
      elif self.is3D:
        self._numpyCartesian = np.float64((self.x, self.y, self.z))
      else:
        self._numpyCartesian = np.float64((self.x, self.y))
    return self._numpyCartesian

  @property
  def asNumpyPolar(self):
    if not hasattr(self, '_numpyPolar'):
      if self.polar:
        coords = 2
        if self.is3D:
          coords += 1
        self._numpyPolar = np.float64(self._point[:coords])
      elif self.is3D:
        self._numpyPolar = np.float64((self.radius, self.azimuth, self.inclination))
      else:
        self._numpyPolar = np.float64((self.length, self.angle))
    return self._numpyPolar

  @property
  def asSgPoint(self):
    if not hasattr(self, '_sgPoint'):
      self._sgPoint = sgPoint(*self.as2Dxy.asNumpyCartesian)
    return self._sgPoint

  @property
  def asKey(self):
    if not hasattr(self, '_key'):
      arr = self.asNumpyCartesian * 100
      self._key = tuple(arr.astype(int))
    return self._key

  @property
  def log(self):
    if self.is3D:
      rep = "(%0.3f, %0.3f, %0.3f)" % self._point
    else:
      rep ="(%0.3f, %0.3f)" % self._point[:2]
    if self.polar:
      rep = "P" + rep
    return rep

  @property
  def as2Dxy(self):
    pt = self.__class__(self.x, self.y)
    return pt

  @property
  def as2Dxz(self):
    return self.__class__(self.x, self.z)

  @property
  def as2Dyz(self):
    return self.__class__(self.y, self.z)

  def __arithmetic(self, other, op):
    if self.polar:
      raise PolarArithmeticError("Can't perform operation on polar coordinates")
    length = 2
    if self.is3D:
      length += 1
    if isinstance(other, Point):
      other = other._point
    return self.__class__([op(a, b) for a, b in zip(self._point[:length], other[:length])])

  def __add__(self, other):
    return self.__arithmetic(other, operator.add)

  def __sub__(self, other):
    return self.__arithmetic(other, operator.sub)

  def __eq__(self, other):
    return self.is3D == other.is3D \
      and math.isclose(self.x, other.x) and math.isclose(self.y, other.y) \
      and (not self.is3D or math.isclose(self.z, other.z))

  def __repr__(self):
    return "%s: %s" % (self.__class__.__name__, self.log)

class Line:
  def __init__(self, point1, point2, relative=None):
    if not isinstance(point1, Point):
      raise TypeError("point1 is not a Point", type(point1))
    if not isinstance(point2, Point):
      raise TypeError("point2 is not a Point", type(point2))
    if point1.is3D != point2.is3D:
      raise ValueError("Cannot mix 2D and 3D points", point1, point2)

    # Always convert polar points to cartesian
    self._origin = point1.asCartesian
    self._end = point2.asCartesian

    if relative:
      self._end = self._end + self._origin
    return

  def shortestLineBetween(self, aLine):
    a0 = self._origin.asNumpyCartesian
    a1 = self._end.asNumpyCartesian
    b0 = aLine._origin.asNumpyCartesian
    b1 = aLine._end.asNumpyCartesian

    A = a0 - b0
    B = a1 - a0
    C = b1 - b0

    parchk = np.cross(a1-a0, b1-b0)

    rad_zero = True
    # Radius is greater than 1e-5 if at least one of the members is greater than 1e-5 (or all three are 5e-6, or 2 of them are 7e-6)
    if parchk[0] > 1e-5 or parchk[0] < -1e-5 or parchk[1] > 1e-5 or parchk[1] < -1e-5 or parchk[2] > 1e-5 or parchk[2] < -1e-5:
      rad_zero = False
    if rad_zero:
      return None

    # Radius is def greater since we already know parchk[i] > 1e-5
    ma = ((np.dot(A, C)*np.dot(C, B)) - (np.dot(A, B)*np.dot(C, C))) \
      / ((np.dot(B, B)*np.dot(C, C)) - (np.dot(C, B)*np.dot(C, B)))
    mb = (ma*np.dot(C, B) + np.dot(A, C)) / np.dot(C, C)

    Pa = a0 + B * ma
    Pb = b0 + C * mb
    return Line(Point(Pa), Point(Pb))

  def intersection(self, aLine):
    if self.is3D != aLine.is3D:
      raise TypeError("Cannot mix 2D and 3D lines")
    if self.is3D:
      shortest = self.shortestLineBetween(aLine)
      if shortest is not None \
         and np.isclose(shortest.length, 0, rtol=1e-05, atol=1e-08, equal_nan=False):
        return shortest._origin
      return None

    xdiff = (self.x1 - self.x2, aLine.x1 - aLine.x2)
    ydiff = (self.y1 - self.y2, aLine.y1 - aLine.y2)

    def det(a, b):
      return a[0] * b[1] - a[1] * b[0]

    div = det(xdiff, ydiff)
    if div == 0:
      return None

    d = (det(self._origin.asNumpyCartesian, self._end.asNumpyCartesian),
         det(aLine._origin.asNumpyCartesian, aLine._end.asNumpyCartesian))
    x = det(d, xdiff) / div
    y = det(d, ydiff) / div
    return Point((x, y))

  def isPointOnLine(self, point):
    if self.is3D != point.is3D:
      raise TypeError("Cannot mix 2D and 3D coordinates")
    ll = self.length
    lp1 = Line(self._origin, point).length
    lp2 = Line(self._end, point).length
    dist = lp1 + lp2 - ll
    if np.isclose(dist, 0, rtol=1e-05, atol=1e-08, equal_nan=False):
      return True
    return False

  def angleDiff(self, other):
    if self.is3D != other.is3D:
      raise TypeError("Cannot mix 2D and 3D lines")
    a = other.angle - self.angle
    a %= 360.0
    if a > 180:
      a = 360 - a
    return a

  def __repr__(self):
    return "Line: %s %s" % (self._origin.__repr__(), self._end.__repr__())

  @property
  def origin(self):
    return self._origin

  @property
  def end(self):
    return self._end

  @property
  def x1(self):
    return self._origin.x

  @property
  def y1(self):
    return self._origin.y

  @property
  def z1(self):
    return self._origin.z

  @property
  def x2(self):
    return self._end.x

  @property
  def y2(self):
    return self._end.y

  @property
  def z2(self):
    return self._end.z

  @property
  def length(self):
    return self.radius

  @property
  def angle(self):
    return self.azimuth

  @property
  def radius(self):
    delta = self._end - self._origin
    return delta.length

  @property
  def azimuth(self):
    delta = self._end - self._origin
    return delta.azimuth

  @property
  def inclination(self):
    delta = self._end - self._origin
    return delta.inclination

  @property
  def is3D(self):
    return self._origin.is3D
