// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include <opencv2/core.hpp>
#include <pybind11/chrono.h>
#include <pybind11/eigen.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <chrono>
#include <vector>

namespace py = pybind11;

PYBIND11_MODULE(types, types)
{
  types.doc() = R"pbdoc(
    Helper data types
    -----------------------
    )pbdoc";

  // tracking module

  // Expose the opencv matrix as a pybind11 buffer, only for 2D matrix of double
  py::class_<cv::Mat>(types, "Mat", py::buffer_protocol(), "2D array class using the py::buffer_protocol. It represents a Matrix as 2D array of double precision data. Use numpy.array(mat) to access data.").def_buffer([](cv::Mat &mat) -> py::buffer_info {
    return py::buffer_info(mat.data,                                /* Pointer to buffer */
                           sizeof(double),                          /* Size of one scalar */
                           py::format_descriptor<double>::format(), /* Python struct-style format descriptor */
                           mat.dims,                                /* Number of dimensions */
                           {mat.rows, mat.cols},                    /* Buffer dimensions */
                           {sizeof(double) * mat.cols,              /* Strides (in bytes) for each index */
                            sizeof(double)});
  })
  .def("__repr__", [](const cv::Mat& mat) {
      return "robot_vision.extensions.types.Mat(): Use numpy.array(Mat()) to access data.";});
}
