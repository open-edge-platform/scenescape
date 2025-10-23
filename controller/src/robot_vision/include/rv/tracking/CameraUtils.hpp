// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <opencv2/opencv.hpp>
#include <tuple>

namespace rv {

/**
 * @brief Convert pixel coordinates to undistorted normalized image coordinates using camera intrinsics and distortion matrices.
 *
 * Compute the undistorted coordinates for the given pixel point and its opposite corner.
 *
 * @param x X-coordinate of the top-left corner of the pixel region (in pixels)
 * @param y Y-coordinate of the top-left corner of the pixel region (in pixels)
 * @param width Width of the pixel region (in pixels)
 * @param height Height of the pixel region (in pixels)
 * @param camera_intrinsics_matrix Camera intrinsics matrix as a cv::Mat
 * @param distortion_matrix Distortion coefficients matrix as a cv::Mat
 *
 * @return Tuple containing:
 *   - X-coordinate of the undistorted point (in normalized image coordinates)
 *   - Y-coordinate of the undistorted point (in normalized image coordinates)
 *   - Width of the undistorted region (in normalized image coordinates)
 *   - Height of the undistorted region (in normalized image coordinates)
 */
std::tuple<double, double, double, double> computePixelsToMeterPlane(
    double x,
    double y,
    double width,
    double height,
    const cv::Mat& camera_intrinsics_matrix,
    const cv::Mat& distortion_matrix
);

} // namespace rv