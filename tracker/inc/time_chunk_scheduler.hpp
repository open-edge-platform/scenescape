// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "scene_registry.hpp"
#include "time_chunk_buffer.hpp"
#include "tracking_worker.hpp"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>

namespace tracker {

/**
 * @brief Timer-based dispatcher for time-chunked detection processing.
 *
 * Runs a timer loop that periodically:
 * 1. Collects all buffered detections via pop_all()
 * 2. Groups them by scope (scene+category)
 * 3. Dispatches to per-scope TrackingWorkers
 *
 * Workers are created lazily on first detection for each scope, up to
 * the configured max_workers limit.
 *
 * Thread-safety: All methods are thread-safe.
 */
class TimeChunkScheduler {
public:
    /**
     * @brief Construct scheduler with configuration.
     *
     * @param buffer Reference to shared TimeChunkBuffer
     * @param registry Reference to SceneRegistry for scene name lookup
     * @param config Tracking configuration
     * @param publish_callback Callback for workers to publish results
     */
    TimeChunkScheduler(TimeChunkBuffer& buffer, const SceneRegistry& registry,
                       const TrackingConfig& config, PublishCallback publish_callback);

    /// Destructor stops scheduler and all workers
    ~TimeChunkScheduler();

    // Non-copyable, non-movable
    TimeChunkScheduler(const TimeChunkScheduler&) = delete;
    TimeChunkScheduler& operator=(const TimeChunkScheduler&) = delete;
    TimeChunkScheduler(TimeChunkScheduler&&) = delete;
    TimeChunkScheduler& operator=(TimeChunkScheduler&&) = delete;

    /**
     * @brief Start the scheduler timer loop.
     */
    void start();

    /**
     * @brief Stop the scheduler and gracefully shutdown all workers.
     *
     * Sends sentinel chunks to all workers and waits for them to finish.
     */
    void stop();

    /**
     * @brief Check if scheduler is running.
     */
    [[nodiscard]] bool is_running() const { return running_.load(); }

    /**
     * @brief Get current number of active workers.
     */
    [[nodiscard]] size_t worker_count() const;

    /**
     * @brief Get total chunks dispatched.
     */
    [[nodiscard]] int dispatched_count() const { return dispatched_count_.load(); }

    /**
     * @brief Get total chunks dropped due to max_workers limit.
     */
    [[nodiscard]] int scope_limit_drops() const { return scope_limit_drops_.load(); }

private:
    /**
     * @brief Scheduler main loop.
     */
    void run();

    /**
     * @brief Wait for the next chunk interval.
     */
    void wait_for_interval();

    /**
     * @brief Dispatch buffered data to workers.
     *
     * @param snapshot Buffer snapshot from pop_all()
     */
    void dispatch(BufferMap&& snapshot);

    /**
     * @brief Get or create a worker for a scope.
     *
     * @param scope Tracking scope
     * @return Pointer to worker, or nullptr if max_workers reached
     */
    TrackingWorker* get_or_create_worker(const TrackingScope& scope);

    /**
     * @brief Build a Chunk from camera map data.
     *
     * @param scope Tracking scope
     * @param cameras Camera data map
     * @return Chunk ready for dispatch
     */
    Chunk build_chunk(const TrackingScope& scope, CameraMap&& cameras);

    TimeChunkBuffer& buffer_;
    const SceneRegistry& registry_;
    TrackingConfig config_;
    PublishCallback publish_callback_;

    std::chrono::milliseconds interval_;
    std::thread scheduler_thread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> stop_requested_{false};
    std::mutex cv_mutex_;
    std::condition_variable cv_;

    mutable std::mutex workers_mutex_;
    std::unordered_map<TrackingScope, std::unique_ptr<TrackingWorker>, TrackingScopeHash> workers_;

    std::atomic<int> dispatched_count_{0};
    std::atomic<int> scope_limit_drops_{0};
};

} // namespace tracker
