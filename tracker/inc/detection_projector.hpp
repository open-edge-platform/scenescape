// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <optional>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

#include <rv/tracking/TrackedObject.hpp>

#include "coordinate_transformer.hpp"
#include "object_class.hpp"
#include "reid_sighting.hpp"
#include "scene_loader.hpp"
#include "tracking_types.hpp"

namespace tracker {

/**
 * @brief Source of world-space geometry for camera detections.
 *
 * A projector sets geometry only: position, size, zMeasured, measurement noise when known and,
 * from a supplied rotation, world yaw with attributes["has_orientation"]. The detection's own
 * data (id, metadata, confidence, ReID) is attached afterwards by toTrackerInputs(), the same
 * way for every projector.
 */
class DetectionProjector {
public:
    virtual ~DetectionProjector() = default;

    /**
     * @brief Project the detections of the camera frames of one chunk.
     *
     * @param batches Camera frames, each with its detections
     * @return One entry per batch, in input order; std::nullopt for a camera the projector
     *         cannot project, whose batch is then skipped.
     */
    virtual std::vector<std::optional<ProjectedDetections>>
    project(std::span<const DetectionBatch> batches) = 0;
};

/**
 * @brief Projects detections with the calibrated model of their camera (CoordinateTransformer):
 *        pixel boxes onto the ground plane, sensor-frame translations through the camera pose.
 */
class CameraModelProjector final : public DetectionProjector {
public:
    /**
     * @param cameras Calibrated cameras by camera_id; batches from other cameras are skipped
     * @param object_class Per-category projection settings (shift_type, footprint_half)
     */
    CameraModelProjector(const std::unordered_map<std::string, Camera>& cameras,
                         const ObjectClassConfig& object_class);

    std::vector<std::optional<ProjectedDetections>>
    project(std::span<const DetectionBatch> batches) override;

private:
    std::unordered_map<std::string, CoordinateTransformer> transformers_;
};

/**
 * @brief Attach the detections' own data to their projected geometry.
 *
 * Sets id (InvalidObjectId when absent), the metadata.* attributes with their confidences,
 * attributes["confidence"] and, for pixel-box detections, the current-chunk ReID sighting token.
 * Detections without geometry are dropped.
 *
 * @param detections Detections of one camera frame
 * @param projected Geometry of `detections`, with one entry per detection
 * @param sightings Optional chunk-local context for tagging ReID observations
 * @throws std::invalid_argument if `projected` does not cover `detections`, or the context does
 *         not reference the exact detection span.
 * @return Tracker inputs in detection order.
 */
std::vector<rv::tracking::TrackedObject>
toTrackerInputs(std::span<const Detection> detections, ProjectedDetections projected,
                const std::optional<ReidSightingContext>& sightings = std::nullopt);

} // namespace tracker
