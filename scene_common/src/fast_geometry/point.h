/*
 * SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
 * SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
 * This file is licensed under the Limited Edge Software Distribution License Agreement.
 */

#ifndef POINT_H
#define POINT_H

#include <vector>
#include <string>
#include <tuple>

#include <pybind11/stl.h>
#include <pybind11/numpy.h>

#define POINT_IS_CLOSE  (1e-9)

typedef unsigned int uint;

namespace py = pybind11;

class Point {
  public:

    // constructors
    Point();
    Point(const Point & p );
    Point(std::vector<double> v, bool isPolar=false);
    Point(double x, double y, bool isPolar=false);
    Point(double x, double y, double z, bool isPolar=false);

    // base properties
    double x() const;
    double y() const;
    double z() const;
    bool is3D() const;
    bool polar() const;
    double radius() const;
    double length() const;
    double azimuth() const;
    double angle() const;
    double inclination() const;

    // conversion
    std::tuple<int, int> cv() const;
    Point asCartesian() const;
    Point asPolar() const;
    std::string repr() const;
    std::string log() const;
    std::vector<double> asCartesianVector() const;
    py::array_t<double> asNumpyCartesian() const;

    // basic arithmetic operations
    Point operator+(const Point &p) const;
    Point operator+(const std::tuple<double, double>& t) const;
    Point operator+(const std::tuple<double, double, double>& t) const;
    void operator+=(const Point &p);
    Point operator-(const Point &p) const;
    Point operator-(const std::tuple<double, double>& t) const;
    Point operator-(const std::tuple<double, double, double>& t) const;
    void operator-=(const Point &p);
    bool operator==(const Point &p) const;
    Point& operator=(const Point& p);

    // extra conversions
    Point as2Dxy() const;
    Point as2Dxz() const;
    Point as2Dyz() const;

    // To avoid creating a Line object and then computing the distance
    double distance(const Point & p) const;
    // Gets the point between current and Point p
    Point midpoint(const Point & p) const;

  private:
    double _x;
    double _y;
    double _z;
    bool _polar;
    bool _is3D;

    // Helper functions, not exposed
    double xFromPolar() const;
    double yFromPolar() const;
    double zFromPolar() const;

    double radiusFromCartesian() const;
    double azimuthFromCartesian() const;
    double inclinationFromCartesian() const;

    // These methods are used to throw exceptions when operating on incompatible points
    inline void checkPointIsCartesian() const;
    inline void checkPointsMatchSpace(const Point & p) const;
};

#endif
