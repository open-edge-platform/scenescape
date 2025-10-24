// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <opencv2/opencv.hpp>
#include <tuple>

namespace rv {

/// Bounding box with position and dimensions
struct BoundingBox {
    double x, y, width, height;
};

/// Camera calibration parameters
struct CameraParams {
    const cv::Mat& intrinsics;
    const cv::Mat& distortion;
};

/// Convert pixel bounding box to undistorted coordinates
BoundingBox computePixelsToMeterPlane(
    const BoundingBox& bbox,
    const CameraParams& params
);

} // namespace rv
