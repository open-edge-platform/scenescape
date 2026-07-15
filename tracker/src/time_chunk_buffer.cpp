// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "time_chunk_buffer.hpp"

#include "metrics.hpp"

#include <utility>

namespace tracker {

void TimeChunkBuffer::add(const TrackingScope& scope, const std::string& camera_id,
                          DetectionBatch&& batch) {
    std::lock_guard lock(mutex_);
    auto& cameras = buffer_[scope];
    if (cameras.find(camera_id) != cameras.end()) {
        // Overwriting an un-dispatched frame for this camera within the scope.
        Metrics::inc_time_chunking_duplicated_cameras(
            {{kAttrScene, scope.scene_id}, {kAttrCategory, scope.category}});
    }
    cameras[camera_id] = std::move(batch);
}

BufferMap TimeChunkBuffer::pop_all() {
    std::lock_guard lock(mutex_);
    BufferMap snapshot = std::move(buffer_);
    buffer_.clear();
    return snapshot;
}

bool TimeChunkBuffer::empty() const {
    std::lock_guard lock(mutex_);
    return buffer_.empty();
}

size_t TimeChunkBuffer::scope_count() const {
    std::lock_guard lock(mutex_);
    return buffer_.size();
}

} // namespace tracker
