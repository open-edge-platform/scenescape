// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "tracking_types.hpp"

#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>

namespace tracker {

constexpr int kWorkerQueueCapacity = 2;

/**
 * @brief Callback type for publishing tracked objects.
 *
 * @param scene_id Scene identifier
 * @param scene_name Human-readable scene name
 * @param category Object category
 * @param timestamp ISO 8601 timestamp
 * @param tracks Vector of tracked objects
 */
using PublishCallback = std::function<void(
    const std::string& scene_id, const std::string& scene_name, const std::string& category,
    const std::string& timestamp, const std::vector<Track>& tracks)>;

/**
 * @brief Per-scope worker thread for processing detection chunks.
 *
 * Each worker owns a bounded queue and processes chunks independently.
 * Currently uses stubbed pass-through tracking; RobotVision integration
 * will be added in a future PR.
 *
 * Thread-safety: Queue operations are thread-safe. Worker runs on its own thread.
 */
class TrackingWorker {
public:
    /**
     * @brief Construct and start a worker for a specific scope.
     *
     * @param scope Tracking scope (scene_id + category)
     * @param scene_name Human-readable scene name
     * @param queue_capacity Maximum chunks in queue (drops current on full)
     * @param publish_callback Callback to publish tracking results
     */
    TrackingWorker(TrackingScope scope, std::string scene_name, int queue_capacity,
                   PublishCallback publish_callback);

    /// Destructor joins worker thread
    ~TrackingWorker();

    // Non-copyable, non-movable (owns thread)
    TrackingWorker(const TrackingWorker&) = delete;
    TrackingWorker& operator=(const TrackingWorker&) = delete;
    TrackingWorker(TrackingWorker&&) = delete;
    TrackingWorker& operator=(TrackingWorker&&) = delete;

    /**
     * @brief Attempt to enqueue a chunk for processing.
     *
     * If queue is full, the chunk is dropped (backpressure handling).
     *
     * @param chunk Chunk to enqueue
     * @return true if enqueued, false if dropped due to full queue
     */
    bool try_enqueue(Chunk&& chunk);

    /**
     * @brief Push a sentinel chunk to signal shutdown.
     *
     * This bypasses the queue capacity check to ensure shutdown signal
     * is always delivered.
     */
    void push_sentinel();

    /**
     * @brief Get current queue depth.
     */
    [[nodiscard]] size_t queue_depth() const;

    /**
     * @brief Get the scope this worker handles.
     */
    [[nodiscard]] const TrackingScope& scope() const { return scope_; }

    /**
     * @brief Get count of chunks processed.
     */
    [[nodiscard]] int processed_count() const { return processed_count_.load(); }

    /**
     * @brief Get count of chunks dropped due to full queue.
     */
    [[nodiscard]] int dropped_count() const { return dropped_count_.load(); }

private:
    /**
     * @brief Worker thread main loop.
     */
    void run();

    /**
     * @brief Process a single chunk (stubbed tracking).
     *
     * @param chunk Chunk to process
     */
    void process_chunk(const Chunk& chunk);

    /**
     * @brief Stub tracking: convert detections to dummy tracks.
     *
     * @param chunk Input chunk with detections
     * @return Vector of tracks with dummy world coordinates
     */
    std::vector<Track> stub_tracking(const Chunk& chunk);

    TrackingScope scope_;
    std::string scene_name_;
    int queue_capacity_;
    PublishCallback publish_callback_;

    std::thread worker_thread_;
    mutable std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::deque<Chunk> queue_;

    std::atomic<bool> stop_requested_{false};
    std::atomic<int> processed_count_{0};
    std::atomic<int> dropped_count_{0};
};

} // namespace tracker
