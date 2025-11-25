// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <opencv2/opencv.hpp>
#include <tuple>

namespace rv {

/// Camera calibration parameters
struct CameraParams {
    const cv::Mat& intrinsics;
    const cv::Mat& distortion;
};

/// Convert pixel bounding box to undistorted coordinates
cv::Rect2f computePixelsToMeterPlane(
    const cv::Rect2f& bbox,
    const CameraParams& params
);

/// Convert multiple pixel bounding boxes to undistorted coordinates (batch processing)
std::vector<cv::Rect2f> computePixelsToMeterPlane(
    const std::vector<cv::Rect2f>& bboxes,
    const CameraParams& params
);

} // namespace rv
