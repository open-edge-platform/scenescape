// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include <map>
#include <vector>
#include <cmath>
#include <sstream>

#include "utils.h"
#include "line.h"

Line::Line(double x1, double y1, double x2, double y2)
      : _origin(x1, y1, false),
        _end(x2,y2, false)
{
}
Line::Line(const Point & p1, const Point &p2, bool relative)
    : _origin(p1.asCartesian()),
      _end(p2.asCartesian())
{
    if(this->_origin.is3D() != this->_end.is3D())
    {
        throw std::invalid_argument("Cannot mix 2D and 3D points\n");
    }
    if(relative)
    {
        this->_end += this->_origin;
    }
}
inline void Line::checkLinesMatchSpace(const Line & l) const
{
    if(this->is3D() != l.is3D())
    {
        throw std::invalid_argument("Cannot mix 2D and 3D lines!\n");
    }
}
std::pair<double, double> Line::getStartPoint() const
{
    return {this->_origin.x(), this->_origin.y()};
}
std::pair<double, double> Line::getEndPoint() const
{
    return {this->_end.x(), this->_end.y()};
}
bool Line::isPointOnLine(const Point & pt) const
{
    if(this->is3D() != pt.is3D())
    {
        throw std::invalid_argument("Cannot mix 2D and 3D coordinates!\n");
    }
    double x1 = this->_origin.x();
    double x2 = this->_end.x();
    double y1 = this->_origin.y();
    double y2 = this->_end.y();
    double px = pt.x();
    double py = pt.y();

    // Check if the point (px, py) is within the bounding box of the line segment
    if (std::min(x1, x2) <= px && px <= std::max(x1, x2) &&
        std::min(y1, y2) <= py && py <= std::max(y1, y2))
    {
        // Check if the point is on the line defined by the endpoints
        double crossProduct = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1);
        // if 0, then point is considered to lie on the line.
        return (std::abs(crossProduct) <= LINE_IS_CLOSE);
    }
    return false; // Point is out of bounds
}
std::tuple<bool, std::pair<double, double>> Line::intersection(const Line& other) const
{
    this->checkLinesMatchSpace(other);
    double x1 = this->_origin.x();
    double x2 = this->_end.x();
    double y1 = this->_origin.y();
    double y2 = this->_end.y();
    double x3 = other._origin.x();
    double x4 = other._end.x();
    double y3 = other._origin.y();
    double y4 = other._end.y();
    double denominator = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1);
    if(std::abs(denominator) <= LINE_IS_CLOSE)
    {
        return std::make_tuple(false, std::make_pair(0.0, 0.0)); // Lines are parallel
    }
    double ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denominator;
    double x = x1 + ua * (x2 - x1);
    double y = y1 + ua * (y2 - y1);
    return std::make_tuple(true, std::make_pair(x, y)); // Intersection point
}
double Line::length()
{
    double delta_x = this->_origin.x() - this->_end.x();
    double delta_y = this->_origin.y() - this->_end.y();
    if(this->is3D())
    {
        double delta_z = this->_origin.z() - this->_end.z();
        return magnitude(delta_x, delta_y, delta_z);
    }
    return magnitude(delta_x, delta_y);
}
std::string Line::repr() const
{
    std::ostringstream result;
    result << "Line: " << this->_origin.repr() << " " << this->_end.repr();
    return result.str();
}
double Line::angleDiff(const Line & l) const
{
    this->checkLinesMatchSpace(l);
    double angle = l.angle() - this->angle();
    angle = std::fmod(angle, 360.0f);
    if(angle < 0.0f)
    {
        angle += 360.0f;
    }
    if(angle > 180.0f)
    {
        angle = 360.0f - angle;
    }
    return angle;
}
Point Line::origin() const
{
    return this->_origin;
}
Point Line::end() const
{
    return this->_end;
}
double Line::x1() const
{
    return this->_origin.x();
}
double Line::y1() const
{
    return this->_origin.y();
}
double Line::z1() const
{
    return this->_origin.z();
}
double Line::x2() const
{
    return this->_end.x();
}
double Line::y2() const
{
    return this->_end.y();
}
double Line::z2() const
{
    return this->_end.z();
}
double Line::radius()
{
    return this->length();
}
double Line::angle() const
{
    return this->azimuth();
}
double Line::azimuth() const
{
    Point delta = this->_end - this->_origin ;
    return delta.azimuth();
}
double Line::inclination() const
{
    Point delta = this->_end - this->_origin ;
    return delta.inclination();
}
bool Line::is3D() const
{
    return this->_origin.is3D();
}
