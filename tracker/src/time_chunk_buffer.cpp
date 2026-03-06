// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "time_chunk_buffer.hpp"

#include <utility>

namespace tracker {

void TimeChunkBuffer::add(const TrackingScope& scope, const std::string& camera_id,
                          DetectionBatch&& batch) {
    std::lock_guard lock(mutex_);
    buffer_[scope][camera_id] = std::move(batch);
    category_cache_[scope.scene_id].insert(scope.category);
}

void TimeChunkBuffer::updateScene(const std::string& scene_id, const DetectionBatch& batch) {
    std::lock_guard lock(mutex_);
    for (const auto& category : category_cache_[scene_id]) {
        TrackingScope scope{scene_id, category};
        auto& camera_map = buffer_[scope];
        // Insert empty batch if camera_id not present, otherwise keep existing batch
        camera_map.try_emplace(batch.camera_id, batch);
    }
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
