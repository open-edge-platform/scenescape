// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include "point.h"
#include "line.h"
#include "rectangle.h"
#include "polygon.h"


namespace py = pybind11;

// Note:
// Be *extra* careful with py::init<> here.
// Unless the py::init<arglist> is explicit and matches very closely the constructors
// pybind might try to guess and create unintended intermediate objects
// and end up calling a 'wrong' constructor.
// An example of this is :
// class declaration:
// class Rectangle {
// public:
//    Rectangle( const Point & origin, const std::vector<double> & size );
//    Rectangle( const Point & origin, const Point & opposite );
// (bindings for Rectangle):
//        .def(py::init<Point, std::vector<double>>(),
//            py::arg("origin"), py::arg("size"))
//        .def(py::init<Point, Point>(),
//            py::arg("origin"), py::arg("opposite"))
// (python):     center_of_mass = Rectangle(origin=Point(int(bounds.x + comw), int(bounds.y + comh)),
//                                 size=[comw, comh])
// might end up calling Rectangle( Point, Point ), even though it should VERY clearly be Rectangle( Point, std::vector ).
// especially considering the py::arg declaration and the use of 'size'.
//

PYBIND11_MODULE( LIBRARY_NAME, m) {
    py::class_<Point>(m, "Point")
        .def(py::init<double, double, bool>(),
            py::arg("x"), py::arg("y"), py::arg("polar") = false )
        .def(py::init<double, double, double, bool>(),
            py::arg("x"), py::arg("y"), py::arg("z"), py::arg("polar") = false )
        .def(py::init<std::vector<double>, bool>(),
            py::arg("data"), py::arg("polar") = false )
        .def_property_readonly("x", &Point::x)
        .def_property_readonly("y", &Point::y)
        .def_property_readonly("z", &Point::z)
        .def_property_readonly("cv", &Point::cv)
        .def_property_readonly("is3D", &Point::is3D)
        .def_property_readonly("radius", &Point::radius)
        .def_property_readonly("length", &Point::length)
        .def_property_readonly("azimuth", &Point::azimuth)
        .def_property_readonly("angle", &Point::angle)
        .def_property_readonly("inclination", &Point::inclination)
        .def_property_readonly("asPolar", &Point::asPolar)
        .def_property_readonly("asCartesian", &Point::asCartesian)
        .def("midpoint", &Point::midpoint)
        .def("distance", &Point::distance)
        .def("__add__", [](const Point& p1, const Point& p2) {
            return p1 + p2;
        })
        .def("__add__", [](const Point& p, const std::tuple<double, double>& t) {
            return p + t;
        })
        .def("__add__", [](const Point& p, const std::tuple<double, double, double>& t) {
            return p + t;
        })
        .def("__sub__", [](const Point& p1, const Point& p2) {
            return p1 - p2;
        })
        .def("__sub__", [](const Point& p, const std::tuple<double, double>& t) {
            return p - t;
        })
        .def("__sub__", [](const Point& p, const std::tuple<double, double, double>& t) {
            return p - t;
        })
        .def("__eq__", &Point::operator==)
        .def("__iadd__", &Point::operator+=)
        .def("__isub__", &Point::operator-=)
        .def_property_readonly("asCartesian", &Point::asCartesian)
        .def_property_readonly("asPolar", &Point::asPolar)
        .def_property_readonly("as2Dxy", &Point::as2Dxy)
        .def_property_readonly("as2Dxz", &Point::as2Dxz)
        .def_property_readonly("as2Dyz", &Point::as2Dyz)
        .def_property_readonly("asCartesianVector",&Point::asCartesianVector)
        .def_property_readonly("asNumpyCartesian",&Point::asNumpyCartesian)
        .def_property_readonly("log", &Point::log)
        .def("__repr__", &Point::repr);

    py::class_<Line>(m, "Line")
        .def(py::init<double, double, double, double>())
        .def(py::init<Point &, Point &, bool>(),
            py::arg("p1"), py::arg("p2"), py::arg("relative") = false )
        .def("isPointOnLine", &Line::isPointOnLine)
        .def("intersection",  &Line::intersection)
        .def_property_readonly("origin", &Line::origin)
        .def_property_readonly("end", &Line::end)
        .def_property_readonly("x1", &Line::x1)
        .def_property_readonly("y1", &Line::y1)
        .def_property_readonly("z1", &Line::z1)
        .def_property_readonly("x2", &Line::x2)
        .def_property_readonly("y2", &Line::y2)
        .def_property_readonly("z2", &Line::z2)
        .def_property_readonly("length", &Line::length)
        .def_property_readonly("radius", &Line::radius)
        .def_property_readonly("angle", &Line::angle)
        .def_property_readonly("azimuth", &Line::azimuth)
        .def_property_readonly("inclination", &Line::inclination)
        .def_property_readonly("is3D", &Line::is3D)
        .def("angleDiff", &Line::angleDiff)
        .def("__repr__", &Line::repr);

    py::class_<Rectangle>(m, "Rectangle")
        .def(py::init<const Point &, const std::vector<double> &>(),
            py::arg("origin"), py::arg("size"))
        .def(py::init<const Point &, const Point &>(),
            py::arg("origin"), py::arg("opposite"))
        .def(py::init<const Point &, const py::tuple &>(),
            py::arg("origin"), py::arg("size"))
        .def(py::init<std::unordered_map<std::string, double> &>())
        .def_property_readonly("size", &Rectangle::size)
        .def_property_readonly("is3D", &Rectangle::is3D)
        .def_property_readonly("width", &Rectangle::width)
        .def_property_readonly("height", &Rectangle::height)
        .def_property_readonly("depth", &Rectangle::depth)
        .def_property_readonly("origin", &Rectangle::origin)
        .def_property_readonly("opposite", &Rectangle::opposite)
        .def_property_readonly("bottomLeft", &Rectangle::bottomLeft)
        .def_property_readonly("bottomRight", &Rectangle::bottomRight)
        .def_property_readonly("topLeft", &Rectangle::topLeft)
        .def_property_readonly("topRight", &Rectangle::topRight)
        .def_property_readonly("cv", &Rectangle::cv)
        .def_property_readonly("x1", &Rectangle::x1)
        .def_property_readonly("y1", &Rectangle::y1)
        .def_property_readonly("x2", &Rectangle::x2)
        .def_property_readonly("y2", &Rectangle::y2)
        .def_property_readonly("x", &Rectangle::x)
        .def_property_readonly("y", &Rectangle::y)
        .def_property_readonly("z", &Rectangle::z)
        .def_property_readonly("area", &Rectangle::area)
        .def_property_readonly("asDict", &Rectangle::asDict)
        .def("__repr__", &Rectangle::repr)
        .def("isPointWithin", &Rectangle::isPointWithin)
        .def("offset", &Rectangle::offset)
        .def("intersection", &Rectangle::intersection);


    py::class_<Size>(m, "Size")
        .def(py::init<double, double>(),
            py::arg("x"), py::arg("y"))
        .def(py::init<double, double, double>(),
            py::arg("x"), py::arg("y"), py::arg("z"))
        .def_property_readonly("width", &Size::width)
        .def_property_readonly("height", &Size::height)
        .def_property_readonly("depth", &Size::depth)
        .def_property_readonly("is3D", &Size::is3D)
        .def_property_readonly("log", &Size::log)
        .def("__repr__", &Size::repr)
        .def_property_readonly("asNumpy", &Size::asNumpy);

    py::class_<Polygon>(m, "Polygon")
        .def(py::init<const std::vector<std::pair<double, double>>&>())
        .def("getVertices", &Polygon::getVertices)
        .def("isPointInside", &Polygon::isPointInside);

}
