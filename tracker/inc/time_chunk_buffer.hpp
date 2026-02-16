// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "tracking_types.hpp"

#include <mutex>

namespace tracker {

/**
 * @brief Thread-safe buffer for aggregating detections into time-aligned chunks.
 *
 * Implements keep-latest semantics: each camera slot within a scope holds only
 * the most recent detection batch. When multiple frames arrive from the same
 * camera before a chunk is dispatched, only the latest is retained.
 *
 * Thread-safety: All methods are thread-safe. Uses mutex protection with
 * atomic swap for efficient bulk retrieval.
 */
class TimeChunkBuffer {
public:
    /**
     * @brief Add a detection batch to the buffer.
     *
     * Upserts the batch: creates scope entry if new, replaces camera data
     * within scope if already exists (keep-latest semantics).
     *
     * @param scope Tracking scope (scene_id + category)
     * @param camera_id Camera identifier
     * @param batch Detection batch to add
     */
    void add(const TrackingScope& scope, const std::string& camera_id, DetectionBatch&& batch);

    /**
     * @brief Atomically retrieve and clear all buffered data.
     *
     * Returns a snapshot of all buffered data and clears the internal buffer.
     * This is the primary consumption method, called by the scheduler.
     *
     * @return BufferMap containing all scopes and their camera data
     */
    [[nodiscard]] BufferMap pop_all();

    /**
     * @brief Check if buffer is empty.
     */
    [[nodiscard]] bool empty() const;

    /**
     * @brief Get current number of scopes in buffer.
     */
    [[nodiscard]] size_t scope_count() const;

private:
    mutable std::mutex mutex_;
    BufferMap buffer_;
};

} // namespace tracker
