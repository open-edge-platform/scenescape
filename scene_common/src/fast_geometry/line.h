/*
 * SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
 * SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
 * This file is licensed under the Limited Edge Software Distribution License Agreement.
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
