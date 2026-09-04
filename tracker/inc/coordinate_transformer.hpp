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
 * @brief Batch-oriented transformer from detections to world-space TrackedObjects.
 *
 * Handles two kinds of detections:
 * - Pixel-space (bounding_box_px): converted via camera intrinsics/extrinsics and
 *   ground-plane ray casting. The foot point (bottom-center of each bbox) determines
 *   the world position; three additional corner points (BL, BR, TL) determine the
 *   object's world-space dimensions.
 * - Sensor-local 3-D pose (translation/size/[rotation], e.g. LiDAR): already a 3-D
 *   point in the sensor's local frame, transformed to world space via the sensor's
 *   pose (extrinsics) directly - no ground-plane ray casting.
 *
 * Designed for high-throughput (1000+ detections per batch):
 * - Single cv::undistortPoints call for all pixel-space detections in the batch
 * - Data-oriented layout: contiguous pixel arrays for cache efficiency
 * - OpenMP parallelization of pose-transform and ray-plane intersection
 *
 * Transformation pipeline per pixel-space detection (4 pixels each):
 * 1. Collect pixels: foot (bottom-center), bottom-left, bottom-right, top-left
 * 2. Batch undistort all 4*N pixels via cv::undistortPoints()
 * 3. Pose-transform + ray-plane intersection (z=0) with OpenMP
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
     * @brief Batch-transform detections to world-space TrackedObjects.
     *
     * Pixel-space detections (bounding_box_px) project 4 bbox pixels (foot, BL, BR, TL)
     * through the full undistort → pose → ray-plane pipeline in a single batched
     * operation; world position comes from the foot point, world size from corner
     * distances. Sensor-local 3-D detections (translation/size/[rotation], e.g. LiDAR)
     * are transformed directly via the sensor's pose (extrinsics only, no ray casting);
     * world size is the detection's size as-is, and yaw (if rotation is present) is the
     * composed sensor-pose + detection rotation, projected to the Z axis.
     *
     * Detections where any projection fails, or that have neither a valid pixel bbox
     * nor a valid 3-D pose, are silently skipped.
     *
     * @param detections Span of detections (pixel-space or sensor-local 3-D)
     * @return TrackedObjects with world-space position and size fields populated.
     *         id, x, y, z, length, width, height are set. Velocity is zero; yaw is set
     *         only for 3-D detections that carry a rotation.
     *         attributes["metadata_json"] is set from Detection::metadata_json when non-empty.
     *         attributes["confidence"] is set from Detection::confidence when present.
     *         attributes["source"] is set from Detection::source when present.
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
     * @brief Batch project pixels to world coordinates on the ground plane.
     *
     * Single cv::undistortPoints call for all pixels, then parallel
     * pose-transform + ray-plane intersection.
     *
     * @param pixels Input pixel coordinates
     * @param[out] world Output world coordinates (pre-allocated, same size as pixels)
     * @param[out] valid Output validity flags (pre-allocated, same size as pixels)
     */
    void batchPixelToWorld(const std::vector<cv::Point2f>& pixels, std::vector<cv::Point2d>& world,
                           std::vector<uint8_t>& valid) const;

    /**
     * @brief Transform the pixel-space detections at `indices` into `result`/`detection_valid`.
     *
     * Detections not referenced by `indices` are left untouched (handled elsewhere).
     */
    void transformPixelDetections(std::span<const Detection> detections,
                                  const std::vector<size_t>& indices,
                                  std::vector<rv::tracking::TrackedObject>& result,
                                  std::vector<uint8_t>& detection_valid) const;

    /**
     * @brief Transform a single sensor-local 3-D detection (translation/size/[rotation])
     * into a world-space TrackedObject via the sensor's pose (extrinsics) only.
     *
     * @pre detection.translation and detection.size are set.
     */
    rv::tracking::TrackedObject transformPoseDetection(const Detection& detection) const;

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
    cv::Matx33d pose_rotation_; ///< Upper-left 3x3 (rotation*scale) block of pose_matrix_
    cv::Point3d camera_origin_;

    static constexpr double kFallbackHorizonDistance = 100.0;
    static constexpr double kEarthRadius = 6371000.0;
    static constexpr double kMinHeightForHorizon = 0.1;
    static constexpr double kRayEpsilon = 1e-6;

    /// Number of pixels projected per detection (foot, BL, BR, TL)
    static constexpr size_t kPixelsPerDetection = 4;
};

} // namespace tracker
