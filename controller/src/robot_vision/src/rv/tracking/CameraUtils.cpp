// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/CameraUtils.hpp"

namespace rv {

cv::Rect2f computePixelsToMeterPlane(
    const cv::Rect2f& bbox,
    const CameraParams& params
) {
    // Undistort top-left and bottom-right corners
    std::vector<cv::Point2f> points = {
        {bbox.x, bbox.y},
        {bbox.x + bbox.width, bbox.y + bbox.height}
    };
    std::vector<cv::Point2f> undistorted;

    cv::undistortPoints(points, undistorted, params.intrinsics, params.distortion);

    return cv::Rect2f(
        undistorted[0].x,
        undistorted[0].y,
        undistorted[1].x - undistorted[0].x,
        undistorted[1].y - undistorted[0].y
    );
}

std::vector<cv::Rect2f> computePixelsToMeterPlane(
    const std::vector<cv::Rect2f>& bboxes,
    const CameraParams& params
) {
    std::vector<cv::Rect2f> results;
    results.reserve(bboxes.size());
    
    for (const auto& bbox : bboxes) {
        results.push_back(computePixelsToMeterPlane(bbox, params));
    }
    
    return results;
}

} // namespace rv
