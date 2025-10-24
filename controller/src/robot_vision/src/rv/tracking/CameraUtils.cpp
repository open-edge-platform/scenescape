// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/CameraUtils.hpp"

namespace rv {

BoundingBox computePixelsToMeterPlane(
    const BoundingBox& bbox,
    const CameraParams& params
) {
    // Undistort top-left and bottom-right corners
    std::vector<cv::Point2f> points = {
        {static_cast<float>(bbox.x), static_cast<float>(bbox.y)},
        {static_cast<float>(bbox.x + bbox.width), static_cast<float>(bbox.y + bbox.height)}
    };
    std::vector<cv::Point2f> undistorted;

    cv::undistortPoints(points, undistorted, params.intrinsics, params.distortion);

    return {
        static_cast<double>(undistorted[0].x),
        static_cast<double>(undistorted[0].y),
        static_cast<double>(undistorted[1].x - undistorted[0].x),
        static_cast<double>(undistorted[1].y - undistorted[0].y)
    };
}

} // namespace rv
