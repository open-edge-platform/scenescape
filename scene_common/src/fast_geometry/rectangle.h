/*
 * SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
 * SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
 * This file is licensed under the Limited Edge Software Distribution License Agreement.
 */

#ifndef RECTANGLE_H
#define RECTANGLE_H

#include <tuple>
#include <unordered_map>
#include <vector>

#include <pybind11/pybind11.h>

#include "point.h"

namespace py = pybind11;

class Size {
public:
    Size(double x, double y);
    Size(double x, double y, double z);

    double height() const;
    double width() const;
    double depth() const;
    py::array_t<double> asNumpy() const;
    std::string log() const;
    std::string repr() const;
    bool is3D() const;
private:
    double _x, _y, _z;
};

class Rectangle {
  public:
    // Constructors
    Rectangle( const Point & origin, const Point & opposite );
    Rectangle( const Point & origin, const std::vector<double> & size );
    Rectangle( const Point & origin, const py::tuple &size );
    Rectangle( const py::tuple & origin, const py::tuple &size, bool relative=false );
    Rectangle(std::unordered_map<std::string, double> & dict);

    // Properties
    //std::tuple<double, double> size();
    Size size();

    double x() const;
    double y() const;
    double z() const;
    double x1() const;
    double y1() const;
    double x2() const;
    double y2() const;
    double width() const;
    double height() const;
    double depth() const;

    bool is3D() const;

    std::string repr() const;

    Point topLeft() const;
    Point topRight() const;
    Point bottomLeft() const;
    Point bottomRight() const;

    const Point & origin();
    const Point & opposite();

    std::tuple<std::tuple<int, int>, std::tuple<int,int>> cv() const;
    double area() const;

    py::dict asDict() const;

    //bool isPointWithin(const py::tuple & coord) const;
    bool isPointWithin(const Point & coord) const;

    Rectangle offset(const Point & p);
    Rectangle intersection(const Rectangle & r);

private:

    Point _origin;
    Point _opposite;
};

#endif

