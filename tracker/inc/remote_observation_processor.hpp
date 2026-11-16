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

#include "object_class.hpp"
#include "observation_processor.hpp"
#include "remote_observation_processor_config.hpp"
#include "scene_loader.hpp"
#include "tracking_types.hpp"

namespace tracker {

struct ServiceConfig;

/// Camera frame of pixel-box detections sent for observation processor.
struct ObservationProcessorFrame {
    std::string camera_id;
    std::chrono::system_clock::time_point timestamp;
    std::vector<cv::Rect2f> boxes; ///< Raw image pixels; the detection_id of a box is its index
};

/// One measurement of a reply as received; RemoteObservationProcessor validates it.
struct RemoteMeasurement {
    std::string detection_id;
    /// MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE: no measurement; the detection keeps the local
    /// local processing without a failure. Every other entry is validated.
    bool unobservable = false;
    /// 7 values: x, y, z (centre), length, width, height, yaw. Empty unless the status is
    /// MEASUREMENT_STATUS_OK with a measurement, so that malformed entries (OK without a
    /// measurement, UNSPECIFIED or unknown statuses) fail validation.
    std::vector<double> mean;
    std::vector<double> noise_covariance; ///< 49 values: 7x7 row-major R
};

/// Reply for one frame.
struct ObservationProcessorReply {
    std::string error; ///< Empty on success, else the failure reason (gRPC status name)
    std::vector<RemoteMeasurement> measurements;

    [[nodiscard]] bool ok() const { return error.empty(); }
};

/**
 * @brief Transport to the observation processor service
 *        (observation_processor/proto/observation_processor.proto).
 */
class ObservationProcessorClient {
public:
    virtual ~ObservationProcessorClient() = default;

    /**
     * @brief Process the camera frames of one tracking scope, concurrently and under one deadline.
     * @return One reply per frame, in input order. Failures are reported in the replies.
     */
    virtual std::vector<ObservationProcessorReply>
    processFrames(const std::string& scene_id, const std::string& category, ConditioningMode mode,
                  std::span<const ObservationProcessorFrame> frames) = 0;
};

/**
 * @brief Processes pixel-box detections with the observation processor service, on top of a local
 *        processor.
 *
 * A detection with a valid remote measurement gets its position, size, z_measured and
 * measurement noise R. z is the centre of mass, as received; the worker publishes the footprint
 * base (ZReference::CentreOfMass). Yaw and attributes["has_orientation"] stay as set by the
 * local processor.
 * All other detections keep the local processing: sensor-frame translations, failed calls,
 * unobservable depths and invalid measurements. Failed calls and invalid replies increment
 * tracker.observation_processor.failed_calls and log a rate-limited warning; process() does not
 * throw on remote failures.
 */
class RemoteObservationProcessor final : public ObservationProcessor {
public:
    /// Shortest interval between two failure warnings of one processor.
    static constexpr std::chrono::seconds kWarningInterval{10};

    /// @throws std::invalid_argument if `local` or `client` is null
    RemoteObservationProcessor(TrackingScope scope, std::unique_ptr<ObservationProcessor> local,
                               std::shared_ptr<ObservationProcessorClient> client,
                               ConditioningMode mode);

    std::vector<std::optional<ProcessedObservations>>
    process(std::span<const DetectionBatch> batches) override;

private:
    void applyReply(const std::string& camera_id, const ObservationProcessorReply& reply,
                    std::span<const size_t> detection_indices, ProcessedObservations& geometry);
    void reportFailure(const std::string& camera_id, const std::string& reason);

    TrackingScope scope_;
    std::unique_ptr<ObservationProcessor> local_;
    std::shared_ptr<ObservationProcessorClient> client_;
    ConditioningMode mode_;
    std::chrono::steady_clock::time_point last_warning_{};
    size_t suppressed_warnings_ = 0;
};

/// Creates the observation processor of one tracking scope.
using ObservationProcessorFactory = std::function<std::unique_ptr<ObservationProcessor>(
    const TrackingScope&, const std::unordered_map<std::string, Camera>&,
    const ObjectClassConfig&)>;

/// Connects an observation processor client to the configured endpoint.
using ObservationProcessorClientFactory = std::function<std::shared_ptr<ObservationProcessorClient>(
    const RemoteObservationProcessorConfig&)>;

/**
 * @brief Choose the processor factory for the service configuration.
 *
 * Observation processor (RemoteObservationProcessor over CameraModelProcessor, one client shared by
 * all scopes) when tracking.experimental_observation_processor is set and the endpoint has a host
 * and port. Otherwise, or when `connect` throws, an empty factory: the workers use local
 * processing. The reason is logged.
 */
ObservationProcessorFactory
makeObservationProcessorFactory(const ServiceConfig& config,
                                const ObservationProcessorClientFactory& connect);

} // namespace tracker
