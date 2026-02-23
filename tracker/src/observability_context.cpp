// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "observability_context.hpp"
#include "metrics.hpp"

#include <chrono>

namespace tracker {

void ObservabilityContext::finalize() const {
    if (!receive_time.has_value() || !publish_time.has_value()) {
        return;
    }

    auto elapsed = *publish_time - *receive_time;
    double latency_ms =
        std::chrono::duration_cast<std::chrono::duration<double, std::milli>>(elapsed).count();

    Metrics::record_latency(latency_ms, {{kAttrScene, scene_id}, {kAttrCategory, category}});
}

void ObservabilityContext::abort(const char* reason) const {
    if (!receive_time.has_value()) {
        return;
    }
    Metrics::inc_dropped(
        {{kAttrReason, reason}, {kAttrCameraId, camera_id}, {kAttrScene, scene_id}});
}

} // namespace tracker
