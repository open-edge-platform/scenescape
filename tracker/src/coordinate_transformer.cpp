// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "coordinate_transformer.hpp"

#include <algorithm>
#include <cmath>
#include <vector>

#include <omp.h>
#include <opencv2/calib3d.hpp>

namespace tracker {

CoordinateTransformer::CoordinateTransformer(const CameraIntrinsics& intrinsics,
                                             const CameraExtrinsics& extrinsics) {
    // Build intrinsics matrix K = [fx 0 cx; 0 fy cy; 0 0 1]
    intrinsics_matrix_ = cv::Matx33d(intrinsics.fx, 0.0, intrinsics.cx, 0.0, intrinsics.fy,
                                     intrinsics.cy, 0.0, 0.0, 1.0);

    // Store distortion coefficients [k1, k2, p1, p2]
    distortion_coeffs_ = cv::Vec4d(intrinsics.distortion.k1, intrinsics.distortion.k2,
                                   intrinsics.distortion.p1, intrinsics.distortion.p2);

    // Compute rotation matrix from Euler angles (XYZ order, degrees)
    cv::Matx33d rmat = eulerToRotationMatrix(extrinsics.rotation);

    // Build 4x4 pose matrix: [R | t; 0 0 0 1] * diag(scale)
    cv::Matx44d rt_mat(rmat(0, 0), rmat(0, 1), rmat(0, 2), extrinsics.translation[0], rmat(1, 0),
                       rmat(1, 1), rmat(1, 2), extrinsics.translation[1], rmat(2, 0), rmat(2, 1),
                       rmat(2, 2), extrinsics.translation[2], 0.0, 0.0, 0.0, 1.0);

    cv::Matx44d scale_mat(extrinsics.scale[0], 0.0, 0.0, 0.0, 0.0, extrinsics.scale[1], 0.0, 0.0,
                          0.0, 0.0, extrinsics.scale[2], 0.0, 0.0, 0.0, 0.0, 1.0);

    pose_matrix_ = rt_mat * scale_mat;

    camera_origin_ = cv::Point3d(extrinsics.translation[0], extrinsics.translation[1],
                                 extrinsics.translation[2]);
}

cv::Matx33d
CoordinateTransformer::eulerToRotationMatrix(const std::array<double, 3>& euler_degrees) {
    const double rx = degToRad(euler_degrees[0]);
    const double ry = degToRad(euler_degrees[1]);
    const double rz = degToRad(euler_degrees[2]);

    const double cx = std::cos(rx);
    const double sx = std::sin(rx);
    const double cy = std::cos(ry);
    const double sy = std::sin(ry);
    const double cz = std::cos(rz);
    const double sz = std::sin(rz);

    // R = Rx * Ry * Rz (intrinsic XYZ)
    return cv::Matx33d(cy * cz, -cy * sz, sy, cx * sz + sx * sy * cz, cx * cz - sx * sy * sz,
                       -sx * cy, sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy);
}

void CoordinateTransformer::batchPixelToWorld(const std::vector<cv::Point2f>& pixels,
                                              std::vector<cv::Point2d>& world,
                                              std::vector<uint8_t>& valid) const {
    const auto n = static_cast<int>(pixels.size());
    if (n == 0)
        return;

    world.resize(n);
    valid.resize(n);

    // Phase 2: Single batched undistort for all pixels
    std::vector<cv::Point2f> undistorted(n);
    cv::undistortPoints(pixels, undistorted, intrinsics_matrix_, distortion_coeffs_);

    // Cache pose matrix elements and camera origin for tight loop access
    const double p00 = pose_matrix_(0, 0), p01 = pose_matrix_(0, 1), p02 = pose_matrix_(0, 2);
    const double p03 = pose_matrix_(0, 3);
    const double p10 = pose_matrix_(1, 0), p11 = pose_matrix_(1, 1), p12 = pose_matrix_(1, 2);
    const double p13 = pose_matrix_(1, 3);
    const double p20 = pose_matrix_(2, 0), p21 = pose_matrix_(2, 1), p22 = pose_matrix_(2, 2);
    const double p23 = pose_matrix_(2, 3);
    const double start_x = camera_origin_.x;
    const double start_y = camera_origin_.y;
    const double start_z = camera_origin_.z;
    const double horizon_distance = getHorizonDistance();

    // Phase 3: Parallel pose-transform + ray-plane intersection
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const double nx = undistorted[i].x;
        const double ny = undistorted[i].y;

        // world_pt = pose_matrix * [nx, ny, 1, 1]
        const double wx = p00 * nx + p01 * ny + p02 + p03;
        const double wy = p10 * nx + p11 * ny + p12 + p13;
        const double wz = p20 * nx + p21 * ny + p22 + p23;

        const double ray_x = wx - start_x;
        const double ray_y = wy - start_y;
        const double ray_z = wz - start_z;

        if (ray_z < -kRayEpsilon) [[likely]] {
            // Ray points downward — intersect with ground plane (z=0)
            const double t = -start_z / ray_z;
            world[i] = cv::Point2d(start_x + t * ray_x, start_y + t * ray_y);
        } else {
            // Horizon culling
            const double xy_len = std::sqrt(ray_x * ray_x + ray_y * ray_y);
            if (xy_len > kRayEpsilon) {
                world[i] = cv::Point2d(start_x + (ray_x / xy_len) * horizon_distance,
                                       start_y + (ray_y / xy_len) * horizon_distance);
            } else {
                world[i] = cv::Point2d(start_x, start_y);
            }
        }
        valid[i] = 1;
    }
}

std::vector<rv::tracking::TrackedObject>
CoordinateTransformer::transformDetections(std::span<const Detection> detections) const {
    const auto n = detections.size();
    if (n == 0)
        return {};

    // Phase 1: Collect 4 pixels per detection into contiguous array
    // Layout per detection: [foot, bottom_left, bottom_right, top_left]
    std::vector<cv::Point2f> pixels(n * kPixelsPerDetection);

    for (size_t i = 0; i < n; ++i) {
        const auto& bbox = detections[i].bounding_box_px;
        const size_t base = i * kPixelsPerDetection;

        // Foot: bottom-center of bbox, used as the object's ground contact point
        pixels[base + 0] = {bbox.x + bbox.width / 2.0f, bbox.y + bbox.height};
        // Bottom-left
        pixels[base + 1] = {bbox.x, bbox.y + bbox.height};
        // Bottom-right
        pixels[base + 2] = {bbox.x + bbox.width, bbox.y + bbox.height};
        // Top-left
        pixels[base + 3] = {bbox.x, bbox.y};
    }

    // Phase 2+3: Batch undistort + parallel ray-plane
    std::vector<cv::Point2d> world;
    std::vector<uint8_t> valid;
    batchPixelToWorld(pixels, world, valid);

    // Phase 4: Assemble TrackedObjects from world-projected points
    std::vector<rv::tracking::TrackedObject> result(n);
    std::vector<uint8_t> detection_valid(n);

    const double cam_x = camera_origin_.x;
    const double cam_y = camera_origin_.y;
    const double cam_z = camera_origin_.z;

#pragma omp parallel for schedule(static)
    for (int i = 0; i < static_cast<int>(n); ++i) {
        const size_t base = static_cast<size_t>(i) * kPixelsPerDetection;

        // Check all 4 projections succeeded
        if (!valid[base] || !valid[base + 1] || !valid[base + 2] || !valid[base + 3]) {
            detection_valid[i] = 0;
            continue;
        }

        const auto& foot = world[base + 0];
        const auto& bl = world[base + 1];
        const auto& br = world[base + 2];
        const auto& tl = world[base + 3];

        // Width: distance between bottom-left and bottom-right
        const double dx_w = br.x - bl.x;
        const double dy_w = br.y - bl.y;
        const double width_m = std::sqrt(dx_w * dx_w + dy_w * dy_w);

        // Height: elevation angle geometry
        const double cdx = cam_x - tl.x;
        const double cdy = cam_y - tl.y;
        const double ll1 = std::sqrt(cdx * cdx + cdy * cdy + cam_z * cam_z);
        const double dx_h = tl.x - bl.x;
        const double dy_h = tl.y - bl.y;
        const double ll2 = std::sqrt(dx_h * dx_h + dy_h * dy_h);
        const double elevation_angle = std::atan2(std::abs(cam_z), ll1);
        const double height_m = std::sin(elevation_angle) * ll2;

        auto& obj = result[i];
        obj.id = detections[i].id.value_or(rv::tracking::InvalidObjectId);
        obj.x = foot.x;
        obj.y = foot.y;
        obj.z = 0.0;
        obj.length = width_m; // [width, width, height] convention
        obj.width = width_m;
        obj.height = height_m;

        detection_valid[i] = 1;
    }

    // Compact: remove invalid detections (preserves ordering)
    size_t write = 0;
    for (size_t read = 0; read < n; ++read) {
        if (detection_valid[read]) {
            if (write != read) {
                result[write] = std::move(result[read]);
            }
            ++write;
        }
    }
    result.resize(write);

    return result;
}

std::array<double, 4> CoordinateTransformer::yawToQuaternion(double yaw_radians) {
    double half_yaw = yaw_radians / 2.0;
    return {0.0, 0.0, std::sin(half_yaw), std::cos(half_yaw)};
}

cv::Point3d CoordinateTransformer::getCameraOrigin() const {
    return camera_origin_;
}

double CoordinateTransformer::getHorizonDistance() const {
    const double camera_height = std::abs(camera_origin_.z);

    if (camera_height > kMinHeightForHorizon) {
        return std::sqrt(2.0 * kEarthRadius * camera_height);
    }

    return kFallbackHorizonDistance;
}

} // namespace tracker
