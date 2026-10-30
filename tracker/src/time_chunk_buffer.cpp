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
    auto [it, inserted] = cameras.try_emplace(camera_id);
    auto& slot = it->second;
    if (inserted) {
        slot.latest = std::move(batch);
        return;
    }
    if (batch.ptz_preserve) {
        addPtzBatch(scope, slot, std::move(batch));
        return;
    }
    // Overwriting an un-dispatched frame for this camera within the scope.
    Metrics::inc_time_chunking_duplicated_cameras(
        {{kAttrScene, scope.scene_id}, {kAttrCategory, scope.category}});
    slot.latest = std::move(batch);
}

void TimeChunkBuffer::addPtzBatch(const TrackingScope& scope, CameraSlot& slot,
                                  DetectionBatch&& batch) {
    if (batch.ptz_gated) {
        return; // The slot already keeps the scope's tracks aging
    }
    if (slot.latest.ptz_gated || slot.latest.timestamp == batch.timestamp) {
        if (!slot.latest.ptz_gated) {
            Metrics::inc_time_chunking_duplicated_cameras(
                {{kAttrScene, scope.scene_id}, {kAttrCategory, scope.category}});
        }
        slot.latest = std::move(batch);
        return;
    }
    if (slot.earlier.size() + 1 >= kMaxPtzBatchesPerCameraPerChunk) {
        Metrics::inc_time_chunking_duplicated_cameras(
            {{kAttrScene, scope.scene_id}, {kAttrCategory, scope.category}});
        slot.earlier.erase(slot.earlier.begin());
    }
    slot.earlier.push_back(std::move(slot.latest));
    slot.latest = std::move(batch);
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
