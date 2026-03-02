// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "coordinate_transformer.hpp"
#include "id_map.hpp"
#include "tracking_types.hpp"

#include <rv/tracking/MultipleObjectTracker.hpp>

#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>
#include <unordered_map>

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
 * Uses MultipleObjectTracker for Hungarian-matching-based association
 * and Kalman filter tracking of world-space detections.
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
     * @param tracking_config Configuration for RobotVision tracker
     * @param cameras Map of camera_id to CameraConfig for coordinate transform
     */
    TrackingWorker(TrackingScope scope, std::string scene_name, int queue_capacity,
                   PublishCallback publish_callback, const TrackingConfig& tracking_config,
                   const std::unordered_map<std::string, Camera>& cameras);

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
     * @brief Process a single chunk through tracking pipeline.
     *
     * @param chunk Chunk to process
     */
    void process_chunk(Chunk chunk);

    /**
     * @brief Run Hungarian matching, Kalman update, and ID conversion.
     *
     * Takes already-transformed world-coordinate detections, runs
     * MOT association and Kalman filter update, then converts
     * RobotVision tracks to output Track structs with UUID IDs.
     *
     * @param objects_per_camera Per-camera world-coordinate detections
     * @param chunk Input chunk (for category and debug logging)
     * @param timestamp Canonical timestamp for tracker time advancement
     * @return Vector of reliable tracks in world coordinates
     */
    std::vector<Track>
    match_and_convert(std::vector<std::vector<rv::tracking::TrackedObject>>&& objects_per_camera,
                      const Chunk& chunk, std::chrono::system_clock::time_point timestamp);

    /**
     * @brief Transform pixel detections to world coordinates per camera.
     *
     * @param chunk Input chunk with per-camera detection batches
     * @return Per-camera vectors of TrackedObjects in world coordinates
     */
    std::vector<std::vector<rv::tracking::TrackedObject>> transform_detections(const Chunk& chunk);

    /**
     * @brief Convert RobotVision tracks to output Track structs.
     *
     * Manages the int-to-UUID ID map and maps fields from TrackedObject.
     *
     * @param rv_tracks Reliable tracks from RobotVision
     * @param category Object category for the output tracks
     * @return Vector of Track structs ready for publishing
     */
    std::vector<Track> convert_tracks(const std::vector<rv::tracking::TrackedObject>& rv_tracks,
                                      const std::string& category);

    TrackingScope scope_;
    std::string scene_name_;
    int queue_capacity_;
    PublishCallback publish_callback_;

    // RobotVision tracker instance (Hungarian matching + Kalman filter)
    rv::tracking::MultipleObjectTracker tracker_;

    // Camera coordinate transformers (camera_id -> transformer with intrinsics + extrinsics)
    std::unordered_map<std::string, CoordinateTransformer> transformers_;

    // RobotVision int ID -> UUID v4 string mapping (single-thread access, no mutex)
    std::unordered_map<int32_t, std::string> id_map_;

    std::thread worker_thread_;
    mutable std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::deque<Chunk> queue_;

    std::atomic<bool> stop_requested_{false};
    std::atomic<int> processed_count_{0};
    std::atomic<int> dropped_count_{0};
};

} // namespace tracker
