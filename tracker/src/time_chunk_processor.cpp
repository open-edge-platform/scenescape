#include "time_chunk_processor.h"
#include "time_chunk_scheduler.h"
#include "logger.h"
#include "metrics_manager.h"
#include <quill/LogMacros.h>

TimeChunkProcessor::TimeChunkProcessor(Tracker* tracker, const std::string& scene_id,
                                                                             const std::string& category, int interval_ms,
                                                                             ProcessCallback callback)
        : tracker_(tracker), scene_id_(scene_id), category_(category), interval_(interval_ms),
            callback_(std::move(callback)) {}

TimeChunkProcessor::~TimeChunkProcessor() {
    // Unregister from global scheduler to stop receiving ticks
    TimeChunkScheduler::getInstance().unregisterProcessor(this);
    stop();
}

void TimeChunkProcessor::start() {
    if (running_.exchange(true)) {
        return; // Already running
    }

    worker_thread_ = std::thread(&TimeChunkProcessor::worker_loop, this);
    LOG_INFO(logger::get_logger(), "Started TimeChunkProcessor worker for scene '{}' (interval {}ms)",
             scene_id_, interval_.count());
}

void TimeChunkProcessor::stop() {
    if (!running_.exchange(false)) {
        return; // Not running
    }

    {
        std::lock_guard<std::mutex> lk(work_mtx_);
        has_task_ = true; // wake worker to exit
    }
    work_cv_.notify_all();

    if (worker_thread_.joinable()) {
        worker_thread_.join();
    }

    LOG_INFO(logger::get_logger(), "Stopped TimeChunkProcessor worker for scene '{}'", scene_id_);
}

void TimeChunkProcessor::add_detection(const CameraDetectionMsg& msg) {
    buffer_.add(msg);
}

bool TimeChunkProcessor::try_enqueue_tick() {
    // Pop all buffered detections
    auto detections = buffer_.pop_all();
    if (detections.empty()) {
        return false;
    }

    // If worker or tracker is busy, drop the batch
    if (worker_processing_.load(std::memory_order_acquire) || tracker_->is_busy()) {
        LOG_WARNING(logger::get_logger(), "Tracker is busy. Dropping {} messages for scene: {}",
                    detections.size(), scene_id_);
        auto& metrics = MetricsManager::getInstance();
        for (size_t i = 0; i < detections.size(); ++i) {
            metrics.incrementDropped("tracker_busy");
        }
        return false;
    }

    // Enqueue the batch to worker (move, not copy)
    {
        std::lock_guard<std::mutex> lk(work_mtx_);
        pending_batch_ = std::move(detections);
        has_task_ = true;
    }
    work_cv_.notify_one();
    return true;
}

void TimeChunkProcessor::worker_loop() {
    while (running_.load(std::memory_order_acquire)) {
        std::vector<CameraDetectionMsg> local_batch;
        {
            std::unique_lock<std::mutex> lk(work_mtx_);
            work_cv_.wait(lk, [this]() { return !running_.load(std::memory_order_acquire) || has_task_; });
            if (!running_.load(std::memory_order_acquire)) break;
            if (!has_task_) continue;
            local_batch = std::move(pending_batch_);
            has_task_ = false;
        }

        if (local_batch.empty()) {
            continue;
        }

        worker_processing_.store(true, std::memory_order_release);

        // Measure batch wall-time across all detections and single scene publish
        auto batch_start = std::chrono::steady_clock::now();

        // Compute a representative timestamp for the chunk (latest across the batch)
        std::chrono::system_clock::time_point chunk_ts = local_batch.front().get_timestamp();
        for (const auto& detection : local_batch) {
            auto ts = detection.get_timestamp();
            if (ts > chunk_ts) chunk_ts = ts;
        }

        // Process the entire chunk in one batch; returns final reliable tracks
        auto tracks = tracker_->process_detections_batch(local_batch);

        // Publish one scene-level detection for the chunk; use last camera id for visibility
        const std::string camera_for_visibility = local_batch.back().id;
        callback_(camera_for_visibility, tracks, chunk_ts);

        auto batch_end = std::chrono::steady_clock::now();
        auto batch_duration_ms =
            std::chrono::duration_cast<std::chrono::nanoseconds>(batch_end - batch_start).count() /
            1e6;

        // Record batch duration labeled by category (Controller-compatible)
        auto& metrics = MetricsManager::getInstance();
        metrics.recordTrackingDurationByCategory(batch_duration_ms, category_);

        worker_processing_.store(false, std::memory_order_release);
    }

    LOG_INFO(logger::get_logger(), "TimeChunkProcessor worker loop exiting for scene '{}'",
             scene_id_);
}
