// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/CameraUtils.hpp"

namespace rv {

std::tuple<double, double, double, double> computePixelsToMeterPlane(
    double x,
    double y,
    double width,
    double height,
    const cv::Mat& camera_intrinsics_matrix,
    const cv::Mat& distortion_matrix
) {
    // Create point for top-left corner
    std::vector<cv::Point2f> px_points = {cv::Point2f(static_cast<float>(x), static_cast<float>(y))};
    std::vector<cv::Point2f> undistorted_points;

    // Undistort the top-left point
    cv::undistortPoints(px_points, undistorted_points, camera_intrinsics_matrix, distortion_matrix);

    // Create point for bottom-right corner
    std::vector<cv::Point2f> opposite_px_points = {cv::Point2f(static_cast<float>(x + width), static_cast<float>(y + height))};
    std::vector<cv::Point2f> opposite_undistorted_points;

    // Undistort the bottom-right point
    cv::undistortPoints(opposite_px_points, opposite_undistorted_points, camera_intrinsics_matrix, distortion_matrix);

    // Extract coordinates
    double undist_x = static_cast<double>(undistorted_points[0].x);
    double undist_y = static_cast<double>(undistorted_points[0].y);
    double opposite_undist_x = static_cast<double>(opposite_undistorted_points[0].x);
    double opposite_undist_y = static_cast<double>(opposite_undistorted_points[0].y);

    // Calculate undistorted width and height
    double undist_width = opposite_undist_x - undist_x;
    double undist_height = opposite_undist_y - undist_y;

    return std::make_tuple(undist_x, undist_y, undist_width, undist_height);
}

} // namespace rv