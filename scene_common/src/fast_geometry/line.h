
/*
 * Copyright (C) 2024 Intel Corporation
 *
 * This software and the related documents are Intel copyrighted materials,
 * and your use of them is governed by the express license under which they
 * were provided to you ("License"). Unless the License provides otherwise,
 * you may not use, modify, copy, publish, distribute, disclose or transmit
 * this software or the related documents without Intel's prior written permission.
 *
 * This software and the related documents are provided as is, with no express
 * or implied warranties, other than those that are expressly stated in the License.
 */

#ifndef LINE_H
#define LINE_H

#include <map>
#include <vector>

#include "point.h"

#define LINE_IS_CLOSE   (POINT_IS_CLOSE)

class Line {
  public:
    // Constructors
    Line(double x1, double y1, double x2, double y2);
    Line(const Point & p1, const Point & p2, bool relative=false);

    // origin,end to pair
    std::pair<double, double> getStartPoint() const;
    std::pair<double, double> getEndPoint() const;

    // Check if point lies on a line
    bool isPointOnLine(const Point & pt) const;
    // Get point where two lines intersect
    std::tuple<bool, std::pair<double, double>> intersection(const Line& other) const;

    // Properties
    double length();
    std::string repr() const;
    double angleDiff(const Line & l) const;
    Point origin() const;
    Point end() const;
    double x1() const;
    double y1() const;
    double z1() const;
    double x2() const;
    double y2() const;
    double z2() const;
    double radius();
    double angle() const;
    double azimuth() const;
    double inclination() const;
    bool is3D() const;

  private:
    Point _origin;
    Point _end;
    double _length;

    // Check whether both lines are 2D or 3D
    inline void checkLinesMatchSpace(const Line & l) const;
};

#endif
