// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <cstddef>
#include <functional>
#include <memory>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

#include <opencv2/core.hpp>

#include "detection_projector.hpp"
#include "object_class.hpp"
#include "remote_projection_config.hpp"
#include "scene_loader.hpp"
#include "tracking_types.hpp"

namespace tracker {

struct ServiceConfig;

/// Camera frame of pixel-box detections sent for remote projection.
struct ProjectionFrame {
    std::string camera_id;
    std::chrono::system_clock::time_point timestamp;
    std::vector<cv::Rect2f> boxes; ///< Raw image pixels; the detection_id of a box is its index
};

/// One measurement of a reply as received; RemoteProjector validates it.
struct RemoteMeasurement {
    std::string detection_id;
    bool ok = false;          ///< MEASUREMENT_STATUS_OK with a measurement
    std::vector<double> mean; ///< 7 values: x, y, z (centre), length, width, height, yaw
    std::vector<double> noise_covariance; ///< 49 values: 7x7 row-major R
};

/// Reply for one frame.
struct ProjectionReply {
    std::string error; ///< Empty on success, else the failure reason (gRPC status name)
    std::vector<RemoteMeasurement> measurements;

    [[nodiscard]] bool ok() const { return error.empty(); }
};

/**
 * @brief Transport to the remote projection service (api/projection/v1/projection.proto).
 */
class ProjectionClient {
public:
    virtual ~ProjectionClient() = default;

    /**
     * @brief Project the camera frames of one tracking scope, concurrently and under one deadline.
     * @return One reply per frame, in input order. Failures are reported in the replies.
     */
    virtual std::vector<ProjectionReply> projectFrames(const std::string& scene_id,
                                                       const std::string& category,
                                                       ConditioningMode mode,
                                                       std::span<const ProjectionFrame> frames) = 0;
};

/**
 * @brief Projects pixel-box detections with the remote projection service, on top of a local
 *        projector.
 *
 * A detection with a valid remote measurement gets its position, size, zMeasured and
 * measurement noise R. The centre z is lowered by half the height, to the object base used by
 * the tracker. Yaw and attributes["has_orientation"] stay as set by the local projector.
 * All other detections keep the local projection: sensor-frame translations, failed calls,
 * unobservable depths and invalid measurements. Failed calls and invalid replies increment
 * tracker.remote_projection.failed_calls and log a rate-limited warning; project() does not
 * throw on remote failures.
 */
class RemoteProjector final : public DetectionProjector {
public:
    /// Shortest interval between two failure warnings of one projector.
    static constexpr std::chrono::seconds kWarningInterval{10};

    /// @throws std::invalid_argument if `local` or `client` is null
    RemoteProjector(TrackingScope scope, std::unique_ptr<DetectionProjector> local,
                    std::shared_ptr<ProjectionClient> client, ConditioningMode mode);

    std::vector<std::optional<ProjectedDetections>>
    project(std::span<const DetectionBatch> batches) override;

private:
    void applyReply(const std::string& camera_id, const ProjectionReply& reply,
                    std::span<const size_t> detection_indices, ProjectedDetections& geometry);
    void reportFailure(const std::string& camera_id, const std::string& reason);

    TrackingScope scope_;
    std::unique_ptr<DetectionProjector> local_;
    std::shared_ptr<ProjectionClient> client_;
    ConditioningMode mode_;
    std::chrono::steady_clock::time_point last_warning_{};
    size_t suppressed_warnings_ = 0;
};

/// Creates the detection projector of one tracking scope.
using ProjectorFactory = std::function<std::unique_ptr<DetectionProjector>(
    const TrackingScope&, const std::unordered_map<std::string, Camera>&,
    const ObjectClassConfig&)>;

/// Connects a projection client to the configured endpoint.
using ProjectionClientFactory =
    std::function<std::shared_ptr<ProjectionClient>(const RemoteProjectionConfig&)>;

/**
 * @brief Choose the projector factory for the service configuration.
 *
 * Remote projection (RemoteProjector over CameraModelProjector, one client shared by all scopes)
 * when tracking.experimental_remote_projection is set and the endpoint has a host and port.
 * Otherwise, or when `connect` throws, an empty factory: the workers use local projection. The
 * reason is logged.
 */
ProjectorFactory makeProjectorFactory(const ServiceConfig& config,
                                      const ProjectionClientFactory& connect);

} // namespace tracker
