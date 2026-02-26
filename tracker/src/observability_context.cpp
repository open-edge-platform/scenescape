// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "observability_context.hpp"
#include "metrics.hpp"

#include <chrono>

namespace tracker {

namespace {

/**
 * @brief Compute elapsed milliseconds between two optional time points.
 * @return Duration in ms, or std::nullopt if either time point is unset.
 */
std::optional<double> elapsed_ms(const std::optional<std::chrono::steady_clock::time_point>& start,
                                 const std::optional<std::chrono::steady_clock::time_point>& end) {
    if (!start.has_value() || !end.has_value()) {
        return std::nullopt;
    }
    return std::chrono::duration_cast<std::chrono::duration<double, std::milli>>(*end - *start)
        .count();
}

} // namespace

void ObservabilityContext::finalize() const {
    auto latency_ms = elapsed_ms(receive_time, publish_time);
    if (!latency_ms) {
        return;
    }

    Metrics::record_latency(*latency_ms, {{kAttrScene, scene_id}, {kAttrCategory, category}});

    // Per-stage latency breakdown (informational — no-op when timestamps are missing)
    // Attributes: scene only (no camera_id or category to avoid confusion when chunks mix sources)
    MetricAttributes stage_attrs = {{kAttrScene, scene_id}};

    if (auto ms = elapsed_ms(receive_time, parse_time)) {
        Metrics::record_stage_latency(kMetricStageParse, *ms, stage_attrs);
    }
    if (auto ms = elapsed_ms(parse_time, buffer_time)) {
        Metrics::record_stage_latency(kMetricStageBuffer, *ms, stage_attrs);
    }
    if (auto ms = elapsed_ms(buffer_time, dispatch_time)) {
        Metrics::record_stage_latency(kMetricStageQueue, *ms, stage_attrs);
    }
    if (auto ms = elapsed_ms(dispatch_time, transform_time)) {
        Metrics::record_stage_latency(kMetricStageTransform, *ms, stage_attrs);
    }
    if (auto ms = elapsed_ms(transform_time, track_time)) {
        Metrics::record_stage_latency(kMetricStageTrack, *ms, stage_attrs);
    }
    if (auto ms = elapsed_ms(track_time, publish_time)) {
        Metrics::record_stage_latency(kMetricStagePublish, *ms, stage_attrs);
    }
}

void ObservabilityContext::abort(const char* reason) const {
    if (!receive_time.has_value()) {
        return;
    }
    Metrics::inc_dropped(
        {{kAttrReason, reason}, {kAttrCameraId, camera_id}, {kAttrScene, scene_id}});
}

} // namespace tracker
