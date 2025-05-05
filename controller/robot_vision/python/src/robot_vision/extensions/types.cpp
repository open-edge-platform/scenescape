/*
* ----------------- BEGIN LICENSE BLOCK ---------------------------------
*
* INTEL CONFIDENTIAL
*
* Copyright (c) 2019-2023 Intel Corporation
*
* This software and the related documents are Intel copyrighted materials, and
* your use of them is governed by the express license under which they were
* provided to you (License). Unless the License provides otherwise, you may not
* use, modify, copy, publish, distribute, disclose or transmit this software or
* the related documents without Intel's prior written permission.
*
* This software and the related documents are provided as is, with no express or
* implied warranties, other than those that are expressly stated in the License.
*
* ----------------- END LICENSE BLOCK -----------------------------------
*/

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
