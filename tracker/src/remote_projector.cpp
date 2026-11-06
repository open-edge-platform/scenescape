// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "remote_projector.hpp"

#include "config_loader.hpp"
#include "logger.hpp"
#include "metrics.hpp"

#include <cmath>
#include <optional>
#include <stdexcept>
#include <utility>

namespace tracker {

namespace {

using MeasurementVector = rv::tracking::TrackedObject::MeasurementVector;
using MeasurementMatrix = rv::tracking::TrackedObject::MeasurementMatrix;
constexpr int kMeasurementSize = rv::tracking::TrackedObject::MeasurementSize;

constexpr const char* kReasonInvalidResponse = "invalid_response";
constexpr const char* kReasonInvalidMeasurement = "invalid_measurement";
constexpr const char* kReasonClientError = "client_error";

struct AcceptedMeasurement {
    MeasurementVector mean;
    MeasurementMatrix noise;
};

/// Boxes the service rejects (and with them the whole frame) are not sent.
bool isSendableBox(const cv::Rect2f& box) {
    return std::isfinite(box.x) && std::isfinite(box.y) && std::isfinite(box.width) &&
           std::isfinite(box.height) && box.width >= 0.0f && box.height >= 0.0f;
}

bool isPositiveDefinite(const MeasurementMatrix& matrix) {
    // Cholesky factorization succeeds only for a symmetric positive definite matrix.
    MeasurementMatrix lower = MeasurementMatrix::zeros();
    for (int i = 0; i < kMeasurementSize; ++i) {
        for (int j = 0; j <= i; ++j) {
            double sum = matrix(i, j);
            for (int k = 0; k < j; ++k) {
                sum -= lower(i, k) * lower(j, k);
            }
            if (i == j) {
                if (!(sum > 0.0)) {
                    return false;
                }
                lower(i, i) = std::sqrt(sum);
            } else {
                lower(i, j) = sum / lower(j, j);
            }
        }
    }
    return true;
}

/// Accept a measurement with a finite 7-value mean, positive size and finite SPD 7x7 R.
std::optional<AcceptedMeasurement> acceptMeasurement(const RemoteMeasurement& measurement) {
    constexpr size_t kMeanSize = kMeasurementSize;
    constexpr size_t kCovarianceSize = kMeanSize * kMeanSize;
    if (measurement.mean.size() != kMeanSize ||
        measurement.noise_covariance.size() != kCovarianceSize) {
        return std::nullopt;
    }

    AcceptedMeasurement accepted;
    for (int i = 0; i < kMeasurementSize; ++i) {
        const double value = measurement.mean[static_cast<size_t>(i)];
        if (!std::isfinite(value)) {
            return std::nullopt;
        }
        accepted.mean(i) = value;
    }
    if (!(accepted.mean(3) > 0.0 && accepted.mean(4) > 0.0 && accepted.mean(5) > 0.0)) {
        return std::nullopt;
    }

    MeasurementMatrix covariance;
    for (int i = 0; i < kMeasurementSize; ++i) {
        for (int j = 0; j < kMeasurementSize; ++j) {
            const double value =
                measurement.noise_covariance[static_cast<size_t>(i * kMeasurementSize + j)];
            if (!std::isfinite(value)) {
                return std::nullopt;
            }
            covariance(i, j) = value;
        }
    }
    // Symmetrize as the Python TrackedObject setter does.
    accepted.noise = 0.5 * (covariance + covariance.t());
    if (!isPositiveDefinite(accepted.noise)) {
        return std::nullopt;
    }
    return accepted;
}

void applyMeasurement(const AcceptedMeasurement& measurement, rv::tracking::TrackedObject& object) {
    const auto& mean = measurement.mean;
    object.x = mean(0);
    object.y = mean(1);
    object.z = mean(2);
    object.length = mean(3);
    object.width = mean(4);
    object.height = mean(5);
    object.zMeasured = true;
    object.measurementNoiseCov = measurement.noise;
}

} // namespace

RemoteProjector::RemoteProjector(TrackingScope scope, std::unique_ptr<DetectionProjector> local,
                                 std::shared_ptr<ProjectionClient> client, ConditioningMode mode)
    : scope_(std::move(scope)), local_(std::move(local)), client_(std::move(client)), mode_(mode) {
    if (!local_ || !client_) {
        throw std::invalid_argument("RemoteProjector requires a local projector and a client");
    }
}

std::vector<std::optional<ProjectedDetections>>
RemoteProjector::project(std::span<const DetectionBatch> batches) {
    // Always project locally first; valid remote measurements overwrite it. See "Why local
    // projection runs on every frame" in tracker/docs/implementation.md.
    auto projected = local_->project(batches);
    if (projected.size() != batches.size()) {
        return projected;
    }

    std::vector<ProjectionFrame> frames;
    std::vector<size_t> frame_batches;
    std::vector<std::vector<size_t>> frame_detections;
    for (size_t b = 0; b < batches.size(); ++b) {
        const auto& batch = batches[b];
        // Cameras the local projector cannot project are skipped by the worker.
        if (!projected[b] || !projected[b]->covers(batch.detections.size())) {
            continue;
        }
        ProjectionFrame frame{batch.camera_id, batch.timestamp, {}};
        std::vector<size_t> indices;
        for (size_t d = 0; d < batch.detections.size(); ++d) {
            const auto& detection = batch.detections[d];
            if (detection.translation || !isSendableBox(detection.bounding_box_px)) {
                continue;
            }
            frame.boxes.push_back(detection.bounding_box_px);
            indices.push_back(d);
        }
        if (frame.boxes.empty()) {
            continue;
        }
        frames.push_back(std::move(frame));
        frame_batches.push_back(b);
        frame_detections.push_back(std::move(indices));
    }
    if (frames.empty()) {
        return projected;
    }

    std::vector<ProjectionReply> replies;
    try {
        replies = client_->projectFrames(scope_.scene_id, scope_.category, mode_, frames);
    } catch (const std::exception& e) {
        LOG_DEBUG("Remote projection client error for scope {}/{}: {}", scope_.scene_id,
                  scope_.category, e.what());
        replies.assign(frames.size(), ProjectionReply{kReasonClientError, {}});
    }
    if (replies.size() != frames.size()) {
        replies.assign(frames.size(), ProjectionReply{kReasonInvalidResponse, {}});
    }

    for (size_t f = 0; f < frames.size(); ++f) {
        applyReply(frames[f].camera_id, replies[f], frame_detections[f],
                   *projected[frame_batches[f]]);
    }
    return projected;
}

void RemoteProjector::applyReply(const std::string& camera_id, const ProjectionReply& reply,
                                 std::span<const size_t> detection_indices,
                                 ProjectedDetections& geometry) {
    if (!reply.ok()) {
        reportFailure(camera_id, reply.error);
        return;
    }
    const auto& measurements = reply.measurements;
    if (measurements.size() != detection_indices.size()) {
        reportFailure(camera_id, kReasonInvalidResponse);
        return;
    }
    for (size_t k = 0; k < measurements.size(); ++k) {
        if (measurements[k].detection_id != std::to_string(k)) {
            reportFailure(camera_id, kReasonInvalidResponse);
            return;
        }
    }

    bool invalid_measurement = false;
    for (size_t k = 0; k < measurements.size(); ++k) {
        if (measurements[k].unobservable) {
            continue; // depth unobservable: keep the local projection
        }
        const auto accepted = acceptMeasurement(measurements[k]);
        if (!accepted) {
            invalid_measurement = true;
            continue;
        }
        const size_t index = detection_indices[k];
        applyMeasurement(*accepted, geometry.objects[index]);
        geometry.has_geometry[index] = 1;
    }
    if (invalid_measurement) {
        reportFailure(camera_id, kReasonInvalidMeasurement);
    }
}

void RemoteProjector::reportFailure(const std::string& camera_id, const std::string& reason) {
    Metrics::inc_remote_projection_failed_calls({{kAttrScene, scope_.scene_id.c_str()},
                                                 {kAttrCategory, scope_.category.c_str()},
                                                 {kAttrCameraId, camera_id.c_str()},
                                                 {kAttrReason, reason.c_str()}});

    const auto now = std::chrono::steady_clock::now();
    if (last_warning_ != std::chrono::steady_clock::time_point{} &&
        now - last_warning_ < kWarningInterval) {
        ++suppressed_warnings_;
        return;
    }
    if (suppressed_warnings_ > 0) {
        LOG_WARN("Remote projection failed for scope {}/{}, camera '{}' ({}); using local "
                 "projection ({} more failures since the previous warning)",
                 scope_.scene_id, scope_.category, camera_id, reason, suppressed_warnings_);
    } else {
        LOG_WARN("Remote projection failed for scope {}/{}, camera '{}' ({}); using local "
                 "projection",
                 scope_.scene_id, scope_.category, camera_id, reason);
    }
    last_warning_ = now;
    suppressed_warnings_ = 0;
}

ProjectorFactory makeProjectorFactory(const ServiceConfig& config,
                                      const ProjectionClientFactory& connect) {
    if (!config.tracking.experimental_remote_projection) {
        return {};
    }
    const auto& endpoint = config.infrastructure.remote_projection;
    if (!endpoint || !endpoint->hasEndpoint()) {
        LOG_WARN("Experimental remote projection is enabled, but its host and port are not set; "
                 "using local projection");
        return {};
    }

    std::shared_ptr<ProjectionClient> client;
    try {
        client = connect(*endpoint);
    } catch (const std::exception& e) {
        LOG_ERROR("Experimental remote projection disabled, using local projection: {}", e.what());
        return {};
    }
    if (!client) {
        LOG_ERROR("Experimental remote projection disabled, using local projection: no client");
        return {};
    }

    const auto mode = config.tracking.remote_projection_mode;
    LOG_INFO("Experimental remote projection enabled: {}:{} (mode={}, timeout={}ms, tls={})",
             endpoint->host, endpoint->port, toString(mode), endpoint->timeout_ms,
             !endpoint->insecure);
    const double chunk_interval_ms = 1000.0 / config.tracking.time_chunking_rate_fps;
    if (endpoint->timeout_ms > chunk_interval_ms) {
        LOG_WARN("Remote projection timeout {}ms exceeds the chunk interval {:.1f}ms "
                 "(time_chunking_rate_fps={}); a slow projection service delays tracking",
                 endpoint->timeout_ms, chunk_interval_ms, config.tracking.time_chunking_rate_fps);
    }
    return [client, mode](const TrackingScope& scope,
                          const std::unordered_map<std::string, Camera>& cameras,
                          const ObjectClassConfig& object_class) {
        return std::make_unique<RemoteProjector>(
            scope, std::make_unique<CameraModelProjector>(cameras, object_class), client, mode);
    };
}

} // namespace tracker
