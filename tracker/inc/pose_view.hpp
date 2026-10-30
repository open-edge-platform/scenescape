// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cmath>

#include <opencv2/core.hpp>

namespace tracker {

/**
 * @brief Precomputed camera-to-world pose used by CoordinateTransformer projections.
 *
 * Built once per pose: at construction for the static (home) pose and once per
 * PoseContext for a PTZ pose, so per-batch projection never rebuilds it.
 */
struct PoseView {
    cv::Matx44d pose_matrix = cv::Matx44d::eye(); ///< scene_from_camera (static: R|t * scale)
    cv::Matx33d rotation = cv::Matx33d::eye();    ///< Camera-to-world rotation (no scale)
    cv::Point3d origin;                           ///< Camera position in the scene
    double horizon_distance = kFallbackHorizonDistance;

    static constexpr double kFallbackHorizonDistance = 100.0;
    static constexpr double kEarthRadius = 6371000.0;
    static constexpr double kMinHeightForHorizon = 0.1;

    /**
     * @brief Horizon distance for the camera height (Earth curvature), or the fallback.
     */
    static double horizonDistanceFor(double camera_z) {
        const double camera_height = std::abs(camera_z);
        if (camera_height > kMinHeightForHorizon) {
            return std::sqrt(2.0 * kEarthRadius * camera_height);
        }
        return kFallbackHorizonDistance;
    }

    /**
     * @brief View for a rigid, row-major scene_from_camera matrix (PoseContext).
     */
    static PoseView fromRigidMatrix(const cv::Matx44d& matrix) {
        PoseView view;
        view.pose_matrix = matrix;
        view.rotation =
            cv::Matx33d(matrix(0, 0), matrix(0, 1), matrix(0, 2), matrix(1, 0), matrix(1, 1),
                        matrix(1, 2), matrix(2, 0), matrix(2, 1), matrix(2, 2));
        view.origin = cv::Point3d(matrix(0, 3), matrix(1, 3), matrix(2, 3));
        view.horizon_distance = horizonDistanceFor(view.origin.z);
        return view;
    }
};

} // namespace tracker
