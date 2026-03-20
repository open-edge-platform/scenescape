// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "time_chunk_scheduler.hpp"
#include "logger.hpp"
#include "metrics.hpp"

#include <algorithm>
#include <stdexcept>

namespace tracker {

TimeChunkScheduler::TimeChunkScheduler(TimeChunkBuffer& buffer, const SceneRegistry& registry,
                                       const TrackingConfig& config,
                                       PublishCallback publish_callback)
    : buffer_(buffer), registry_(registry), config_(config),
      publish_callback_(std::move(publish_callback)) {
    // Defense-in-depth: schema and config loader validate this upstream,
    // but guard here to prevent undefined behavior if bypassed.
    if (config_.time_chunking_rate_fps <= 0) {
        throw std::runtime_error("time_chunking_rate_fps must be >= 1, got: " +
                                 std::to_string(config_.time_chunking_rate_fps));
    }
    // Calculate interval from FPS (e.g., 15 FPS = 66.7ms)
    int interval_ms = 1000 / config_.time_chunking_rate_fps;
    interval_ = std::chrono::milliseconds(interval_ms);
    LOG_DEBUG("TimeChunkScheduler interval: {}ms ({}fps)", interval_ms,
              config_.time_chunking_rate_fps);
}

TimeChunkScheduler::~TimeChunkScheduler() {
    stop();
}

void TimeChunkScheduler::start() {
    if (running_.load()) {
        return;
    }

    running_ = true;
    stop_requested_ = false;
    scheduler_thread_ = std::thread(&TimeChunkScheduler::run, this);
    LOG_INFO("TimeChunkScheduler started (interval={}ms, max_workers={})", interval_.count(),
             config_.max_workers);
}

void TimeChunkScheduler::stop() {
    if (!running_.load()) {
        return;
    }

    LOG_INFO("TimeChunkScheduler stopping...");

    // Signal stop
    {
        std::lock_guard lock(cv_mutex_);
        stop_requested_ = true;
    }
    cv_.notify_one();

    // Wait for scheduler thread
    if (scheduler_thread_.joinable()) {
        scheduler_thread_.join();
    }

    // Send sentinels to all workers and let them finish
    {
        std::lock_guard lock(workers_mutex_);
        for (auto& [scope, worker] : workers_) {
            worker->push_sentinel();
        }
    }

    // Workers are joined in their destructors when we clear the map
    {
        std::lock_guard lock(workers_mutex_);
        workers_.clear();
    }

    running_ = false;
    LOG_INFO("TimeChunkScheduler stopped (dispatched={}, scope_limit_drops={})",
             dispatched_count_.load(), scope_limit_drops_.load());
}

size_t TimeChunkScheduler::worker_count() const {
    std::lock_guard lock(workers_mutex_);
    return workers_.size();
}

void TimeChunkScheduler::run() {
    while (!stop_requested_.load()) {
        wait_for_interval();

        if (stop_requested_.load()) {
            break;
        }

        // Collect all buffered data
        BufferMap snapshot = buffer_.pop_all();

        if (!snapshot.empty()) {
            dispatch(std::move(snapshot));
        }
    }
}

void TimeChunkScheduler::wait_for_interval() {
    std::unique_lock lock(cv_mutex_);
    cv_.wait_for(lock, interval_, [this] { return stop_requested_.load(); });
}

void TimeChunkScheduler::dispatch(BufferMap&& snapshot) {
    for (auto& [scope, cameras] : snapshot) {
        auto* worker = get_or_create_worker(scope);
        if (worker == nullptr) {
            // Max workers reached, drop this scope's data
            size_t msg_count = cameras.size();
            scope_limit_drops_.fetch_add(1);
            Metrics::inc_dropped_n(msg_count, {{kAttrScene, scope.scene_id},
                                               {kAttrCategory, scope.category},
                                               {kAttrReason, kReasonDroppedMaxWorkers}});
            LOG_WARN("Dropped chunk for scope {}/{}: max_workers limit ({}) reached, messages={}",
                     scope.scene_id, scope.category, config_.max_workers, msg_count);
            continue;
        }

        Chunk chunk = build_chunk(scope, std::move(cameras));
        if (worker->try_enqueue(std::move(chunk))) {
            dispatched_count_.fetch_add(1);
        }
        // Note: if try_enqueue fails, worker already logged and counted the drop
    }
}

TrackingWorker* TimeChunkScheduler::get_or_create_worker(const TrackingScope& scope) {
    std::lock_guard lock(workers_mutex_);

    // Check if worker already exists
    auto it = workers_.find(scope);
    if (it != workers_.end()) {
        return it->second.get();
    }

    // Check max_workers limit
    if (static_cast<int>(workers_.size()) >= config_.max_workers) {
        return nullptr;
    }

    // Look up scene display name and build camera map
    std::string scene_display_name = scope.scene_id; // Default to ID if not found
    std::unordered_map<std::string, Camera> cameras;

    if (const auto* scene = registry_.find_scene_by_id(scope.scene_id)) {
        scene_display_name = scene->name;
        // Build camera map for this scene
        for (const auto& camera : scene->cameras) {
            cameras[camera.uid] = camera;
        }
    }

    // Create new worker with tracking config and cameras
    auto worker = std::make_unique<TrackingWorker>(scope, scene_display_name, kWorkerQueueCapacity,
                                                   publish_callback_, config_, cameras);

    LOG_INFO("Created TrackingWorker for scope {}/{} (total workers: {}, cameras: {})",
             scope.scene_id, scope.category, workers_.size() + 1, cameras.size());

    auto* ptr = worker.get();
    workers_[scope] = std::move(worker);
    return ptr;
}

Chunk TimeChunkScheduler::build_chunk(const TrackingScope& scope, CameraMap&& cameras) {
    Chunk chunk;
    chunk.scene_id = scope.scene_id;
    chunk.category = scope.category;
    chunk.chunk_time = std::chrono::steady_clock::now();

    // Convert map to vector
    chunk.camera_batches.reserve(cameras.size());
    for (auto& [camera_id, batch] : cameras) {
        chunk.camera_batches.push_back(std::move(batch));
    }

    // Sort by timestamp for deterministic processing order
    std::sort(chunk.camera_batches.begin(), chunk.camera_batches.end(),
              [](const DetectionBatch& a, const DetectionBatch& b) {
                  return a.receive_time < b.receive_time;
              });

    // Propagate earliest batch's observability context to chunk level
    if (!chunk.camera_batches.empty()) {
        chunk.obs_ctx = chunk.camera_batches.front().obs_ctx;
        chunk.obs_ctx.captureDispatchTime();
    }

    return chunk;
}

} // namespace tracker
