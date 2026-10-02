// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <cmath>
#include <numbers>
#include <optional>
#include <span>
#include <vector>

#include <opencv2/core.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "object_class.hpp"
#include "scene_loader.hpp"
#include "tracking_types.hpp"

namespace tracker {

/**
 * @brief Batch-oriented transformer from pixel detections to world-space TrackedObjects.
 *
 * Converts 2D pixel bounding boxes into 3D world positions and sizes using
 * camera intrinsics/extrinsics. The foot point (bottom-center of each bbox)
 * determines the world position via ground-plane intersection; three additional
 * corner points (BL, BR, TL) determine the object's world-space dimensions.
 *
 * Designed for high-throughput (1000+ detections per batch):
 * - Single cv::undistortPoints call for all pixels in the batch
 * - Data-oriented layout: contiguous pixel arrays for cache efficiency
 * - OpenMP parallelization of pose-transform and ray-plane intersection
 *
 * Transformation pipeline per detection (4 pixels each):
 * 1. Collect pixels: foot (bottom-center), bottom-left, bottom-right, top-left
 * 2. Batch undistort all 4*N pixels via cv::undistortPoints()
 * 3. Pose-transform + ray-plane intersection (z=0) with OpenMP
 * 4. Optional TYPE_2 foot re-projection (wide/short objects)
 * 5. Assemble TrackedObjects: position from foot, size from corners
 *
 * Projection modes (shift_type), matching Controller MovingObject.camLoc:
 * - ObjectClassConfig::kShiftType1 (default): bottom-center of the bbox
 * - ObjectClassConfig::kShiftType2: shift foot upward by (height/2)*(baseAngle/90)
 *   before projecting
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
     * @param shift_type Projection mode: ObjectClassConfig::kShiftType1 (default) or
     *        ObjectClassConfig::kShiftType2
     * @param footprint_half_m Optional camloc size offset (metres). When set,
     *        uses this instead of half the projected bbox width — matching
     *        Controller MovingObject.mapObjectDetectionToWorld asset sizes.
     */
    CoordinateTransformer(const CameraIntrinsics& intrinsics, const CameraExtrinsics& extrinsics,
                          int shift_type = ObjectClassConfig::kShiftType1,
                          std::optional<double> footprint_half_m = std::nullopt);

    /**
     * @brief Projection mode used for the detection foot point.
     */
    [[nodiscard]] int shiftType() const { return shift_type_; }

    /**
     * @brief Optional fixed half-footprint used for the camloc bearing offset.
     */
    [[nodiscard]] const std::optional<double>& footprintHalfM() const { return footprint_half_m_; }

    /**
     * @brief Batch-transform detections from pixel space to world-space TrackedObjects.
     *
     * For each detection, projects 4 bbox pixels (foot, BL, BR, TL) through the full
     * undistort → pose → ray-plane pipeline in a single batched operation. Computes
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
    int shift_type_;
    std::optional<double> footprint_half_m_;

    static constexpr double kFallbackHorizonDistance = 100.0;
    static constexpr double kEarthRadius = 6371000.0;
    static constexpr double kMinHeightForHorizon = 0.1;
    static constexpr double kRayEpsilon = 1e-6;

    /// Number of pixels projected per detection (foot, BL, BR, TL)
    static constexpr size_t kPixelsPerDetection = 4;
};

} // namespace tracker
