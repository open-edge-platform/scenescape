// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "tracking_worker.hpp"

#include "logger.hpp"

namespace tracker {

namespace {

/**
 * @brief Generate a unique track ID.
 */
std::string generate_track_id() {
    static std::atomic<uint64_t> counter{0};
    return std::to_string(counter.fetch_add(1));
}

} // namespace

TrackingWorker::TrackingWorker(TrackingScope scope, std::string scene_name, int queue_capacity,
                               PublishCallback publish_callback)
    : scope_(std::move(scope)), scene_name_(std::move(scene_name)), queue_capacity_(queue_capacity),
      publish_callback_(std::move(publish_callback)) {
    worker_thread_ = std::thread(&TrackingWorker::run, this);
}

TrackingWorker::~TrackingWorker() {
    // Signal stop and wake up worker
    {
        std::lock_guard lock(queue_mutex_);
        stop_requested_ = true;
    }
    queue_cv_.notify_one();

    if (worker_thread_.joinable()) {
        worker_thread_.join();
    }
}

bool TrackingWorker::try_enqueue(Chunk&& chunk) {
    std::lock_guard lock(queue_mutex_);

    if (static_cast<int>(queue_.size()) >= queue_capacity_) {
        // Drop current chunk (not oldest) per implementation.md
        dropped_count_.fetch_add(1);
        LOG_WARN("Dropped chunk for scope {}/{}: queue full (capacity={})", scope_.scene_id,
                 scope_.category, queue_capacity_);
        return false;
    }

    queue_.push_back(std::move(chunk));
    queue_cv_.notify_one();
    return true;
}

void TrackingWorker::push_sentinel() {
    {
        std::lock_guard lock(queue_mutex_);
        // Sentinel bypasses capacity check
        queue_.push_back(Chunk::make_sentinel());
    }
    queue_cv_.notify_one();
}

size_t TrackingWorker::queue_depth() const {
    std::lock_guard lock(queue_mutex_);
    return queue_.size();
}

void TrackingWorker::run() {
    LOG_INFO("TrackingWorker started for scope {}/{}", scope_.scene_id, scope_.category);

    while (true) {
        Chunk chunk;
        {
            std::unique_lock lock(queue_mutex_);
            queue_cv_.wait(lock, [this] { return !queue_.empty() || stop_requested_; });

            if (stop_requested_ && queue_.empty()) {
                break;
            }

            if (queue_.empty()) {
                continue;
            }

            chunk = std::move(queue_.front());
            queue_.pop_front();
        }

        // Check for sentinel
        if (chunk.is_sentinel()) {
            LOG_DEBUG("TrackingWorker received sentinel for scope {}/{}", scope_.scene_id,
                      scope_.category);
            break;
        }

        process_chunk(chunk);
    }

    LOG_INFO("TrackingWorker stopped for scope {}/{} (processed={}, dropped={})", scope_.scene_id,
             scope_.category, processed_count_.load(), dropped_count_.load());
}

void TrackingWorker::process_chunk(const Chunk& chunk) {
    if (chunk.camera_batches.empty()) {
        processed_count_.fetch_add(1);
        return;
    }

    auto tracks = stub_tracking(chunk);
    if (tracks.empty() || !publish_callback_) {
        processed_count_.fetch_add(1);
        return;
    }

    const auto& timestamp_iso = chunk.camera_batches.back().timestamp_iso;
    publish_callback_(scope_.scene_id, scene_name_, scope_.category, timestamp_iso, tracks);
    processed_count_.fetch_add(1);
}

std::vector<Track> TrackingWorker::stub_tracking(const Chunk& chunk) {
    std::vector<Track> tracks;

    // Stub: Convert each detection to a track with dummy world coordinates
    // Real RobotVision integration will be added in PR 3
    for (const auto& batch : chunk.camera_batches) {
        for (const auto& detection : batch.detections) {
            Track track;
            track.id = generate_track_id();
            track.category = chunk.category;

            // Dummy world coordinates based on bounding box center
            // Real coordinate transformation will use camera extrinsics
            double center_x = detection.bounding_box_px.x + detection.bounding_box_px.width / 2.0;
            double center_y = detection.bounding_box_px.y + detection.bounding_box_px.height / 2.0;

            // Simple stub: scale pixels to fake meters (divide by 100)
            track.translation = {center_x / 100.0, center_y / 100.0, 0.0};
            track.velocity = {0.0, 0.0, 0.0};
            track.size = {0.5, 0.5, 1.8};          // Default human-ish size
            track.rotation = {0.0, 0.0, 0.0, 1.0}; // Identity quaternion

            tracks.push_back(std::move(track));
        }
    }

    return tracks;
}

} // namespace tracker
