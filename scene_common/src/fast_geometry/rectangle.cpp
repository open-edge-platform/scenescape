// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include <iostream>
#include <sstream>
#include <iomanip>
#include <cstdio>

#include "utils.h"
#include "rectangle.h"
#include "point.h"

Size::Size(double x, double y)
  :_x(x),
   _y(y),
   _z(std::nan("2d"))
{
}

Size::Size(double x, double y, double z)
  :_x(x),
   _y(y),
   _z(z)
{
}
double Size::width() const
{
    return _x;
}
double Size::height() const
{
    return _y;
}
double Size::depth() const
{
    return _z;
}
py::array_t<double> Size::asNumpy() const
{
    if( this->is3D() )
    {
        std::vector<double> result(3) ;
        result[0] = this->width();
        result[1] = this->height();
        result[2] = this->depth();
        return py::array_t<double>(result.size(), result.data());
    }
    std::vector<double> result(2) ;
    result[0] = this->width();
    result[1] = this->height();
    return py::array_t<double>(result.size(), result.data());
}
bool Size::is3D() const
{
    return ! std::isnan(this->_z);
}
std::string Size::repr() const
{
    std::ostringstream result;
    result << "Size: " << this->log();
    return result.str();
}
std::string Size::log() const
{
    std::ostringstream result;
    result << std::fixed << std::setprecision(3);
    result << "(" << this->_x << ", " << this->_y;
    if( this->is3D() )
    {
        result << ", " << this->_z;
    }
    result << ")";
    return result.str();
}

Rectangle::Rectangle(const Point &origin, const Point &opposite)
    : _origin(origin.asCartesian()),
      _opposite(opposite.asCartesian())
{
}
Rectangle::Rectangle(std::unordered_map<std::string, double> & dict)
{
    if( dict.count("z") )
    {
        this->_origin = Point( dict["x"], dict["y"], dict["z"] );
        this->_opposite = Point( this->_origin.x() + dict["width"],
                                 this->_origin.y() + dict["height"],
                                 this->_origin.z() + dict["depth"] );
    }
    else
    {
        this->_origin = Point( dict["x"], dict["y"] );
        this->_opposite = Point( this->_origin.x() + dict["width"],
                                 this->_origin.y() + dict["height"] );
    }
 }
Rectangle::Rectangle(const Point & origin, const std::vector<double> & size)
    : _origin(origin)
{
    if( this->_origin.is3D() )
    {
#ifdef ENABLE_RECTANGLE_CHECKS
        if( size.size() != 3 )
        {
            std::ostringstream errstr;
            errstr << "Invalid size " << size.size() << " for rectangle!\n";
            throw std::invalid_argument(errstr.str());
        }
#endif
        this->_opposite = Point( this->_origin.x() + size[0],
                                 this->_origin.y() + size[1],
                                 this->_origin.z() + size[2] );
    }
    else
    {
#ifdef ENABLE_RECTANGLE_CHECKS
        if( size.size() != 2 )
        {
            std::ostringstream errstr;
            errstr << "Invalid size " << size.size() << " for rectangle!\n";
            throw std::invalid_argument(errstr.str());
        }
#endif
        this->_opposite = Point( this->_origin.x() + size[0],
                                 this->_origin.y() + size[1] );
    }
}

Rectangle::Rectangle(const Point & origin, const py::tuple &size)
    : _origin(origin)
{
    if( this->_origin.is3D() )
    {
#ifdef ENABLE_RECTANGLE_CHECKS
        if( size.size() != 3 )
        {
            std::ostringstream errstr;
            errstr << "Invalid size " << size.size() << " for rectangle!\n";
            throw std::invalid_argument(errstr.str());
        }
#endif
        this->_opposite = Point( this->_origin.x() + size[0].cast<double>(),
                                 this->_origin.y() + size[1].cast<double>(),
                                 this->_origin.z() + size[2].cast<double>() );
    }
    else
    {
#ifdef ENABLE_RECTANGLE_CHECKS
        if( size.size() != 2 )
        {
            std::ostringstream errstr;
            errstr << "Invalid size " << size.size() << " for rectangle!\n";
            throw std::invalid_argument(errstr.str());
        }
#endif
        this->_opposite = Point( this->_origin.x() + size[0].cast<double>(),
                                 this->_origin.y() + size[1].cast<double>() );
    }
}
Rectangle::Rectangle(const py::tuple & origin, const py::tuple &size, bool relative)
{
#ifdef ENABLE_RECTANGLE_CHECKS
    if( origin.size() != size.size()
      || (origin.size() != 3 && origin.size() != 2)
      || (size.size() != 3 && size.size() != 2) )
    {
        std::ostringstream errstr;
        errstr << "Invalid size " << origin.size() << ", " << size.size() << " for rectangle!\n";
        throw std::invalid_argument(errstr.str());
    }
#endif
    if( origin.size() == 3 )
    {
        this->_origin = Point( origin[0].cast<double>(),
                               origin[1].cast<double>(),
                               origin[2].cast<double>() );
        if( relative )
        {
            this->_opposite = Point( this->_origin.x() + size[0].cast<double>(),
                                     this->_origin.y() + size[1].cast<double>(),
                                     this->_origin.z() + size[2].cast<double>() );
        }
        else
        {
            this->_opposite = Point( size[0].cast<double>(),
                                     size[1].cast<double>(),
                                     size[2].cast<double>() );
        }
    }
    else
    {
        this->_origin = Point( origin[0].cast<double>(),
                               origin[1].cast<double>() );
        if( relative )
        {
            this->_opposite = Point( this->_origin.x() + size[0].cast<double>(),
                                     this->_origin.y() + size[1].cast<double>() );
        }
        else
        {
            this->_opposite = Point( size[0].cast<double>(),
                                     size[1].cast<double>() );
        }

    }
}
double Rectangle::x() const
{
    return this->_origin.x();
}
double Rectangle::y() const
{
    return this->_origin.y();
}
double Rectangle::z() const
{
    return this->_origin.z();
}
double Rectangle::x1() const
{
    return this->x();
}
double Rectangle::y1() const
{
    return this->y();
}
double Rectangle::x2() const
{
    return this->_opposite.x();
}
double Rectangle::y2() const
{
    return this->_opposite.y();
}
double Rectangle::width() const
{
    return this->x2() - this->x1();
}
double Rectangle::height() const
{
    return this->y2() - this->y1();
}
double Rectangle::depth() const
{
    return this->_opposite.z() - this->_origin.z();
}
double Rectangle::area() const
{
    return this->width() * this->height();
}
Point Rectangle::bottomLeft() const
{
    return Point( this->x1(), this->y2() );
}
Point Rectangle::bottomRight() const
{
    return Point( this->x2(), this->y2() );
}
Point Rectangle::topLeft() const
{
    return Point( this->x1(), this->y1() );
}
Point Rectangle::topRight() const
{
    return Point( this->x2(), this->y1() );
}
const Point & Rectangle::origin()
{
    return this->_origin;
}
const Point & Rectangle::opposite()
{
    return this->_opposite;
}
Size Rectangle::size()
{
    if( this->is3D() )
    {
        return Size(this->width(), this->height(), this->depth());
    }
    return Size(this->width(), this->height());
}
bool Rectangle::is3D() const
{
    return this->_origin.is3D();
}
std::string Rectangle::repr() const
{
    std::ostringstream result;
    result << "[(" << this->x1() << "," << this->y1() << "), (" << this->x2() << "," << this->y2() << ")]";
    return result.str();
}
std::tuple<std::tuple<int, int>, std::tuple<int,int>> Rectangle::cv() const
{
    return std::make_tuple( this->_origin.cv(), this->_opposite.cv() );
}
py::dict Rectangle::asDict() const
{
    py::dict result;
    result["x"] = this->x();
    result["y"] = this->y();
    result["width"] = this->width();
    result["height"] = this->height();
    if( this->is3D() )
    {
        result["z"] = this->z();
        result["depth"] = this->depth();
    }
    return result;
}
bool Rectangle::isPointWithin(const Point & coord) const
{
    if( coord.x() < this->x()
        || coord.y() < this->y()
        || coord.x() > this->x2()
        || coord.y() > this->y2() )
    {
        return false;
    }
    return true;
}
Rectangle Rectangle::offset(const Point & p)
{
    return Rectangle( Point(p.x() + this->x(), p.y() + this->y()),
                      Point(p.x() + this->x2(), p.y() + this->y2()) );
}
Rectangle Rectangle::intersection(const Rectangle & r)
{
    double x1 = std::max(this->x1(), r.x1());
    double y1 = std::max(this->y1(), r.y1());
    double x2 = std::min(this->x2(), r.x2());
    double y2 = std::min(this->y2(), r.y2());
    if( x1 <= x2
        && y1 <= y2 )
    {
        return Rectangle( Point(x1, y1),
                      Point(x2, y2));
    }
    return Rectangle( Point(0,0), Point(0,0) );
}
