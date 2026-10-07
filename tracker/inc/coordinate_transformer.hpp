// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <cmath>
#include <numbers>
#include <span>
#include <vector>

#include <opencv2/core.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "scene_loader.hpp"
#include "tracking_types.hpp"

namespace tracker {

/**
 * @brief Batch-oriented transformer from pixel detections to world-space TrackedObjects.
 *
 * Converts 2D pixel bounding boxes into 3D world positions and sizes using
 * camera intrinsics/extrinsics. Two opposite bbox corners are undistorted to
 * define a normalized rectangle. Its bottom-center determines world position;
 * the bottom-left, bottom-right, and top-left determine world-space dimensions.
 *
 * Designed for high-throughput (1000+ detections per batch):
 * - Single cv::undistortPoints call for all pixels in the batch
 * - Data-oriented layout: contiguous pixel arrays for cache efficiency
 * - OpenMP parallelization of pose-transform and ray-plane intersection
 *
 * Transformation pipeline per detection:
 * 1. Collect top-left and bottom-right pixels
 * 2. Batch undistort 2*N corners and derive normalized foot, BL, BR, TL
 * 3. Pose-transform + ray-plane intersection (z=0) for 4*N points with OpenMP
 * 4. Assemble TrackedObjects: position from foot, size from corners
 *
 * Euler angle convention:
 * - XYZ INTRINSIC rotation order, angles in DEGREES
 * - R = Rx * Ry * Rz (intrinsic = multiply in same order as letters)
 * - Equivalent to scipy Rotation.from_euler('XYZ', ..., degrees=True)
 */
class CoordinateTransformer {
public:
    /**
     * @brief Construct transformer with camera calibration data.
     *
     * @param intrinsics Camera intrinsic parameters (fx, fy, cx, cy, distortion)
     * @param extrinsics Camera extrinsic parameters (translation, rotation, scale)
     */
    CoordinateTransformer(const CameraIntrinsics& intrinsics, const CameraExtrinsics& extrinsics);

    /**
     * @brief Batch-transform detections from pixel space to world-space TrackedObjects.
     *
     * For each detection, undistorts two opposite bbox corners and derives the
     * normalized foot, BL, BR, TL before batched world projection. Computes
     * world position (from foot point) and world size (from corner distances).
     *
     * Detections where any projection fails are silently skipped.
     *
     * @param detections Span of pixel-space detections (bounding boxes)
     * @return TrackedObjects with world-space position and size fields populated.
     *         id, x, y, z, length, width, height are set. Velocity/yaw are zero.
     *         attributes["metadata_json"] is set from Detection::metadata_json when non-empty.
     *         attributes["confidence"] is set from Detection::confidence when present.
     */
    std::vector<rv::tracking::TrackedObject>
    transformDetections(std::span<const Detection> detections) const;

    /**
     * @brief Convert yaw angle (radians) to quaternion [x, y, z, w].
     *
     * Computes a pure Z-axis rotation quaternion:
     *   q = [0, 0, sin(yaw/2), cos(yaw/2)]
     *
     * @param yaw_radians Yaw angle about Z axis in radians
     * @return Quaternion as [x, y, z, w]
     */
    static std::array<double, 4> yawToQuaternion(double yaw_radians);

    /**
     * @brief Get the camera position in world coordinates.
     */
    cv::Point3d getCameraOrigin() const;

    /**
     * @brief Get the 4x4 pose matrix (camera-to-world transformation).
     */
    const cv::Matx44d& getPoseMatrix() const { return pose_matrix_; }

    /**
     * @brief Get the 3x3 camera intrinsics matrix.
     */
    const cv::Matx33d& getIntrinsicsMatrix() const { return intrinsics_matrix_; }

    /**
     * @brief Get the distortion coefficients.
     */
    const cv::Vec4d& getDistortionCoeffs() const { return distortion_coeffs_; }

private:
    /**
     * @brief Batch project normalized points to world coordinates on the ground plane.
     *
     * Parallel pose-transform + ray-plane intersection.
     *
     * @param normalized Undistorted normalized image-plane coordinates
     * @param[out] world Output world coordinates (same size as normalized)
     * @param[out] valid Output validity flags (same size as normalized)
     */
    void batchNormalizedToWorld(const std::vector<cv::Point2f>& normalized,
                                std::vector<cv::Point2d>& world, std::vector<uint8_t>& valid) const;

    /**
     * @brief Compute 3x3 rotation matrix from Euler angles (XYZ intrinsic, degrees).
     */
    static cv::Matx33d eulerToRotationMatrix(const std::array<double, 3>& euler_degrees);

    /**
     * @brief Convert degrees to radians.
     */
    static double degToRad(double degrees) { return degrees * std::numbers::pi / 180.0; }

    /**
     * @brief Calculate horizon distance based on camera height (Earth curvature).
     */
    double getHorizonDistance() const;

    cv::Matx33d intrinsics_matrix_;
    cv::Vec4d distortion_coeffs_;
    cv::Matx44d pose_matrix_;
    cv::Point3d camera_origin_;

    static constexpr double kFallbackHorizonDistance = 100.0;
    static constexpr double kEarthRadius = 6371000.0;
    static constexpr double kMinHeightForHorizon = 0.1;
    static constexpr double kRayEpsilon = 1e-6;

    static constexpr size_t kCornersPerDetection = 2;
    static constexpr size_t kPointsPerDetection = 4;
};

} // namespace tracker
