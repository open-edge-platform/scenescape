// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include <sstream>
#include <iomanip>
#include <cmath>

#include "utils.h"
#include "point.h"

#define DEG_TO_RADIANS(deg)   ((deg) * M_PI / 180.0f)
#define RADIANS_TO_DEG(rad)   ((rad) * 180.0f / M_PI)


Point::Point()
{
}
Point::Point(std::vector<double> v, bool polar)
{
    if(2 != v.size()
       && 3 != v.size())
    {
        std::ostringstream errstr;
        errstr << "Invalid size " << v.size() << " for point!\n";
        throw std::invalid_argument(errstr.str());
    }
    this->_x = v[0];
    this->_y = v[1];
    if(3 == v.size())
    {
        this->_is3D = true;
        this->_z = v[2];
    }
    else
    {
        this->_is3D = false;
        this->_z = std::nan("2d");
    }
    this->_polar = polar;
}
Point::Point(const Point & p)
{
    this->_x = p._x;
    this->_y = p._y;
    this->_is3D = p._is3D;
    this->_polar = p._polar;
    if(this->_is3D)
    {
        this->_z = p._z;
    }
    else
    {
        this->_z = std::nan("2d");
    }
}
Point::Point(double x, double y, double z, bool polar)
{
    this->_x = x;
    this->_y = y;
    this->_z = z;
    this->_is3D = true;
    this->_polar = polar;
}
Point::Point(double x, double y, bool polar)
{
    this->_x = x;
    this->_y = y;
    this->_z = std::nan("2d");
    this->_is3D = false;
    this->_polar = polar;
}
double Point::x() const
{
    if(this->polar())
    {
        return this->xFromPolar();
    }
    return this->_x;
}
double Point::y() const
{
    if(this->polar())
    {
        return this->yFromPolar();
    }
    return this->_y;
}
double Point::z() const
{
    if(false == this->is3D())
    {
        throw std::invalid_argument("Cannot get Z from 2D point\n");
    }
    if(this->polar())
    {
        return this->zFromPolar();
    }
    return this->_z;
}
bool Point::is3D() const
{
    return this->_is3D;
}
bool Point::polar() const
{
    return this->_polar;
}
double Point::xFromPolar() const
{
    return this->_x * cos(DEG_TO_RADIANS(this->_y));
}
double Point::yFromPolar() const
{
    if(this->is3D())
    {
        return this->_x * cos(DEG_TO_RADIANS(this->_z)) * sin(DEG_TO_RADIANS(this->_y));
    }
    else
    {
        return this->_x * sin(DEG_TO_RADIANS(this->_y));
    }
}
double Point::zFromPolar() const
{
    return this->_x * sin(DEG_TO_RADIANS(this->_z)) * cos(DEG_TO_RADIANS(this->_y));
}
double Point::radiusFromCartesian() const
{
    if(this->is3D())
    {
        return magnitude(this->_x, this->_y, this->_z);
    }
    return magnitude(this->_x, this->_y);
}
double Point::radius() const
{
    if(false == this->polar())
    {
        return radiusFromCartesian();
    }
    return this->_x;
}
double Point::length() const
{
    return this->radius();
}
double Point::azimuthFromCartesian() const
{
    double angle = RADIANS_TO_DEG(atan2(this->_y, this->_x));
    angle = std::fmod(angle, 360.0f);
    if(angle < 0)
    {
        angle += 360;
    }
    return angle;
}
double Point::azimuth() const
{
    if(this->polar())
    {
        return this->_y;
    }
    return this->azimuthFromCartesian();
}
double Point::angle() const
{
    return this->azimuth();
}
double Point::inclinationFromCartesian() const
{
    double mag_xy = magnitude(this->_x, this->_y);
    double angle = RADIANS_TO_DEG(atan2(mag_xy, this->_z));
    angle = std::fmod(90 - angle, 360);
    if(angle < 0)
    {
        angle += 360;
    }
    return angle;
}
double Point::inclination() const
{
    if(false == this->is3D())
    {
        throw std::invalid_argument("Cannot get inclination from 2D point\n");
    }
    if(false == this->polar())
    {
        return inclinationFromCartesian();
    }
    return this->_z;
}
double Point::distance(const Point & p) const
{
    double dist_x = this->_x - p._x;
    double dist_y = this->_y - p._y;
    if(this->is3D())
    {
        double dist_z = this->_z - p._z;
        return magnitude(dist_x, dist_y, dist_z);
    }
    return magnitude(dist_x, dist_y);
}
Point Point::midpoint(const Point & p) const
{
    this->checkPointsMatchSpace(p);
    if(false == this->is3D())
    {
        return Point( this->_x + (p._x - this->_x) / 2,
                      this->_y + (p._y - this->_y) / 2);
    }
    return Point( this->_x + (p._x - this->_x) / 2,
                  this->_y + (p._y - this->_y) / 2,
                  this->_z + (p._z - this->_z) / 2);
}
std::tuple<int, int> Point::cv() const
{
    if(this->is3D())
    {
        std::ostringstream errstr;
        errstr << "Cannot get cv from 3D point";
        throw std::invalid_argument(errstr.str());
    }
    return std::make_tuple(int(this->x()), int(this->y()));
}
Point Point::asCartesian () const
{
    if(this->is3D())
    {
        return Point(this->x(), this->y(), this->z(), false);
    }
    return Point(this->x(), this->y(), false);
}
Point Point::asPolar() const
{
    if(this->is3D())
    {
        return Point(this->radius(), this->azimuth(), this->inclination(), true);
    }
    return Point(this->length(), this->angle(), true);
}
std::string Point::repr() const
{
    std::ostringstream result;
    result << "Point: " << this->log();
    return result.str();
}
std::string Point::log() const
{
    std::ostringstream result;
    result << std::fixed << std::setprecision(3);
    if(this->polar())
    {
        result << "P";
    }
    result << "(" << this->_x << ", " << this->_y;
    if(this->is3D())
    {
        result << ", " << this->_z;
    }
    result << ")";
    return result.str();
}
inline void Point::checkPointsMatchSpace(const Point & p) const
{
    if(this->is3D() != p.is3D())
    {
        throw std::invalid_argument("Cannot mix 3D and 2D points!\n");
    }
}
inline void Point::checkPointIsCartesian() const
{
    if(this->polar())
    {
        throw std::invalid_argument("Cannot do Cartesian math on polar points!\n");
    }
}
Point Point::operator+(const Point &p) const
{
    Point res;
    this->checkPointIsCartesian();
    p.checkPointIsCartesian();
    this->checkPointsMatchSpace(p);
    res._polar = false;
    res._x = this->_x + p._x;
    res._y = this->_y + p._y;
    if(this->is3D())
    {
        res._z = this->_z + p._z;
        res._is3D = true;
    }
    else
    {
        res._is3D = false;
    }
    return res;
}
Point Point::operator+(const std::tuple<double, double>& t) const
{
    if(this->polar())
    {
        throw std::invalid_argument("Cannot do Cartesian math on polar points!\n");
    }
    if(this->is3D())
    {
        throw std::invalid_argument("Cannot mix 3D and 2D points!\n");
    }
    return Point(this->_x + std::get<0>(t),
                 this->_y + std::get<1>(t));
}
Point Point::operator+(const std::tuple<double, double, double>& t) const
{
    if(this->polar())
    {
        throw std::invalid_argument("Cannot do Cartesian math on polar points!\n");
    }
    if(!this->is3D())
    {
        throw std::invalid_argument("Cannot mix 3D and 2D points!\n");
    }
    return Point(this->_x + std::get<0>(t),
                 this->_y + std::get<1>(t),
                 this->_z + std::get<2>(t));
}
void Point::operator+=(const Point &p)
{
    this->checkPointIsCartesian();
    p.checkPointIsCartesian();
    this->checkPointsMatchSpace(p);
    this->_x += p._x;
    this->_y += p._y;
    if(this->is3D())
    {
        this->_z += p._z;
    }
}
Point Point::operator-(const Point &p) const
{
    Point res;
    this->checkPointIsCartesian();
    p.checkPointIsCartesian();
    this->checkPointsMatchSpace(p);
    res._polar = false;
    res._x = this->_x - p._x;
    res._y = this->_y - p._y;
    if(this->is3D())
    {
        res._z = this->_z - p._z;
        res._is3D = true;
    }
    else
    {
        res._is3D = false;
    }
    return res;
}
Point Point::operator-(const std::tuple<double, double>& t) const
{
    if(this->polar())
    {
        throw std::invalid_argument("Cannot do Cartesian math on polar points!\n");
    }
    if(this->is3D())
    {
        throw std::invalid_argument("Cannot mix 3D and 2D points!\n");
    }
    return Point(this->_x - std::get<0>(t),
                 this->_y - std::get<1>(t));
}
Point Point::operator-(const std::tuple<double, double, double>& t) const
{
    if(this->polar())
    {
        throw std::invalid_argument("Cannot do Cartesian math on polar points!\n");
    }
    if(!this->is3D())
    {
        throw std::invalid_argument("Cannot mix 3D and 2D points!\n");
    }
    return Point(this->_x - std::get<0>(t),
                 this->_y - std::get<1>(t),
                 this->_z - std::get<2>(t));
}
void Point::operator-=(const Point &p)
{
    this->checkPointIsCartesian();
    p.checkPointIsCartesian();
    this->checkPointsMatchSpace(p);
    this->_x -= p._x;
    this->_y -= p._y;
    if(this->is3D())
    {
        this->_z -= p._z;
    }
}
bool Point::operator==(const Point &p) const
{
    this->checkPointsMatchSpace(p);
    double delta_x = (this->x() - p.x());
    double delta_y = (this->y() - p.y());
    double delta = delta_x*delta_x + delta_y*delta_y;
    if(this->is3D())
    {
        double delta_z = (this->z() - p.z());
        delta += delta_z*delta_z;
    }
    return delta <= POINT_IS_CLOSE;
}
Point & Point::operator=(const Point &other)
{
    if( this != &other )
    {
        this->_x = other._x;
        this->_y = other._y;
        this->_z = other._z;
        this->_polar = other._polar;
        this->_is3D = other._is3D;
    }
    return *this;
}
Point Point::as2Dxy() const
{
    return Point(this->x(), this->y(), false);
}
Point Point::as2Dxz() const
{
    return Point(this->x(), this->z(), false);
}
Point Point::as2Dyz() const
{
    return Point(this->y(), this->z(), false);
}
std::vector<double> Point::asCartesianVector() const
{
    if(this->is3D())
    {
        std::vector<double> result(3);
        result[0] = this->x();
        result[1] = this->y();
        result[2] = this->z();
        return result;
    }
    else
    {
        std::vector<double> result(2);
        result[0] = this->x();
        result[1] = this->y();
        return result;
    }
}
py::array_t<double> Point::asNumpyCartesian() const
{
    std::vector<double> result = this->asCartesianVector();
    return py::array_t<double>(result.size(), result.data());
}
