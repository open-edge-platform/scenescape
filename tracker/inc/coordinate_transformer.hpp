// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <numbers>
#include <optional>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

#include <opencv2/core.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "object_class.hpp"
#include "scene_loader.hpp"
#include "tracking_types.hpp"

namespace tracker {

/**
 * @brief World-space geometry for the detections of one camera frame, in input order.
 *
 * objects[i] is the geometry of detection i when has_geometry[i] is non-zero; otherwise the
 * detection has no measurement and is not tracked. Objects are stored in place, without
 * std::optional, so that compacting them into tracker inputs moves nothing in the common case.
 */
struct ProcessedObservations {
    std::vector<rv::tracking::TrackedObject> objects;
    std::vector<uint8_t> has_geometry; ///< uint8_t, not bool: written from parallel loops

    /// True when both vectors have one entry per detection.
    [[nodiscard]] bool covers(size_t detection_count) const {
        return objects.size() == detection_count && has_geometry.size() == detection_count;
    }
};

/**
 * @brief Transformer from image or sensor-frame detections to world-space geometry.
 *
 * Converts 2D pixel bounding boxes into 3D world positions and sizes using
 * camera intrinsics/extrinsics. Two opposite bbox corners are undistorted to
 * define a normalized rectangle. Its bottom-center determines world position;
 * the bottom-left, bottom-right, and top-left determine world-space dimensions.
 * The detection's own data (id, metadata, confidence, ReID) is not set here; see
 * toTrackerInputs() in observation_processor.hpp.
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
 * 4. Optional TYPE_2 foot re-projection (wide/short objects)
 * 5. Assemble TrackedObjects: position from foot, size from corners
 *
 * Projection modes (shift_type):
 * - ObjectClassConfig::kShiftType1 (default): bottom-center of the bbox
 * - ObjectClassConfig::kShiftType2:  shift foot upward by (height/2)*(baseAngle/90)
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
     * @param footprint_half Optional camloc size offset in metres. When set,
     *        uses this instead of half the projected bbox width — matching
     *        Controller MovingObject.mapObjectDetectionToWorld asset sizes.
     */
    CoordinateTransformer(const CameraIntrinsics& intrinsics, const CameraExtrinsics& extrinsics,
                          int shift_type = ObjectClassConfig::kShiftType1,
                          std::optional<double> footprint_half = std::nullopt);

    /**
     * @brief Projection mode used for the detection foot point.
     */
    [[nodiscard]] int shiftType() const { return shift_type_; }

    /**
     * @brief Optional fixed half-footprint (metres) used for the camloc bearing offset.
     */
    [[nodiscard]] const std::optional<double>& footprintHalf() const { return footprint_half_; }

    /**
     * @brief Batch-transform detections from pixel space or the sensor frame to world geometry.
     *
     * For each bbox detection, undistorts two opposite bbox corners and derives the
     * normalized foot, BL, BR, TL before batched world projection. Computes
     * world position (from foot point, z = 0) and world size (from corner distances).
     * Detections with a sensor-frame translation and size are pose-transformed
     * directly, keeping their measured z.
     *
     * When present, rotation must be a finite sensor-frame [x, y, z, w]
     * quaternion with norm > 1e-12, as guaranteed by the message parser.
     *
     * @param detections Span of detections (pixel bbox, or sensor-frame translation and size)
     * @return Geometry with one entry per detection; has_geometry is 0 where the projection
     *         failed. x, y, z, length, width, height are set. Velocity is zero.
     *         z_measured is true for translation detections, false for ground-plane projections.
     *         Supplied rotation sets world yaw and attributes["has_orientation"].
     *         id stays InvalidObjectId and no other attributes are set.
     */
    ProcessedObservations transformDetections(std::span<const Detection> detections) const;

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
    cv::Matx33d camera_rotation_;
    cv::Matx44d pose_matrix_;
    cv::Point3d camera_origin_;
    int shift_type_;
    std::optional<double> footprint_half_; // metres

    static constexpr double kFallbackHorizonDistance = 100.0;
    static constexpr double kEarthRadius = 6371000.0;
    static constexpr double kMinHeightForHorizon = 0.1;
    static constexpr double kRayEpsilon = 1e-6;

    static constexpr size_t kCornersPerDetection = 2;
    static constexpr size_t kPointsPerDetection = 4;
};

} // namespace tracker
