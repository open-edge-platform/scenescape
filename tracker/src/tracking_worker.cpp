// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "tracking_worker.hpp"

#include "logger.hpp"
#include "time_utils.hpp"

#include <rv/tracking/ObjectMatching.hpp>
#include <rv/tracking/TrackManager.hpp>

#include <algorithm>
#include <chrono>
#include <numeric>

namespace tracker {

namespace {

/**
 * @brief Build TrackManagerConfig from TrackingConfig.
 */
rv::tracking::TrackManagerConfig build_tracker_config(const TrackingConfig& config) {
    rv::tracking::TrackManagerConfig rv_config;

    // Track lifecycle timing
    rv_config.mMaxUnreliableTime = config.max_unreliable_time_s;
    rv_config.mNonMeasurementTimeDynamic = config.non_measurement_time_dynamic_s;
    rv_config.mNonMeasurementTimeStatic = config.non_measurement_time_static_s;
    rv_config.mSuspendedTrackMaxAgeSecs = 60.0;

    // Kalman filter noise parameters
    rv_config.mDefaultProcessNoise = 1e-4;
    rv_config.mDefaultMeasurementNoise = 2e-1;
    rv_config.mInitStateCovariance = 1.0;

    // Motion models for multi-model Kalman estimator
    rv_config.mMotionModels = {rv::tracking::MotionModel::CV, rv::tracking::MotionModel::CA,
                               rv::tracking::MotionModel::CTRV};

    return rv_config;
}

} // namespace

TrackingWorker::TrackingWorker(TrackingScope scope, std::string scene_name, int queue_capacity,
                               PublishCallback publish_callback,
                               const TrackingConfig& tracking_config,
                               const std::unordered_map<std::string, Camera>& cameras)
    : scope_(std::move(scope)), scene_name_(std::move(scene_name)), queue_capacity_(queue_capacity),
      publish_callback_(std::move(publish_callback)),
      tracker_(build_tracker_config(tracking_config)) {
    // Adapt frame-rate-dependent timing parameters
    tracker_.updateTrackerParams(tracking_config.time_chunking_rate_fps);

    // Build coordinate transformers with full intrinsics + extrinsics
    for (const auto& [camera_id, camera] : cameras) {
        transformers_.emplace(camera_id,
                              CoordinateTransformer(camera.intrinsics, camera.extrinsics));
    }

    LOG_INFO("TrackingWorker initialized with {} cameras for scope {}/{}", cameras.size(),
             scope_.scene_id, scope_.category);

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
    // Compute canonical timestamp once: prefer newest batch, fall back to now.
    auto now = std::chrono::system_clock::now();
    auto track_timestamp =
        chunk.camera_batches.empty() ? now : chunk.camera_batches.back().timestamp;
    std::string timestamp_iso = chunk.camera_batches.empty()
                                    ? formatTimestamp(now)
                                    : chunk.camera_batches.back().timestamp_iso;

    // Run RobotVision tracking (empty batches still advance tracker time for track aging)
    auto tracks = run_tracking(chunk, track_timestamp);

    // Always publish (even with empty tracks — downstream needs heartbeats)
    if (publish_callback_) {
        publish_callback_(scope_.scene_id, scene_name_, scope_.category, timestamp_iso, tracks);
    }

    processed_count_.fetch_add(1);
}

std::vector<std::vector<rv::tracking::TrackedObject>>
TrackingWorker::transform_detections(const Chunk& chunk) {
    std::vector<std::vector<rv::tracking::TrackedObject>> objects_per_camera;
    objects_per_camera.reserve(chunk.camera_batches.size());

    for (const auto& batch : chunk.camera_batches) {
        auto transformer_it = transformers_.find(batch.camera_id);
        if (transformer_it == transformers_.end()) {
            LOG_WARN("Unknown camera '{}' in detection batch, skipping", batch.camera_id);
            continue;
        }
        objects_per_camera.push_back(transformer_it->second.transformDetections(batch.detections));
    }

    return objects_per_camera;
}

std::vector<Track>
TrackingWorker::convert_tracks(const std::vector<rv::tracking::TrackedObject>& rv_tracks,
                               const std::string& category) {
    // Extract active RobotVision IDs for map update
    std::vector<int32_t> active_ids;
    active_ids.reserve(rv_tracks.size());
    for (const auto& t : rv_tracks) {
        active_ids.push_back(t.id);
    }

    // Update ID map: preserve UUIDs for continuing tracks, generate new for new tracks
    id_map_ = update_id_map(id_map_, active_ids);

    std::vector<Track> tracks;
    tracks.reserve(rv_tracks.size());

    for (const auto& rv_track : rv_tracks) {
        Track track;
        track.id = id_map_.at(rv_track.id);
        track.category = category;
        track.translation = {rv_track.x, rv_track.y, rv_track.z};
        track.velocity = {rv_track.vx, rv_track.vy, 0.0};
        track.size = {rv_track.length, rv_track.width, rv_track.height};
        track.rotation = CoordinateTransformer::yawToQuaternion(rv_track.yaw);

        tracks.push_back(std::move(track));
    }

    return tracks;
}

std::vector<Track> TrackingWorker::run_tracking(const Chunk& chunk,
                                                std::chrono::system_clock::time_point timestamp) {
    // Transform pixel detections to world coordinates per camera
    auto objects_per_camera = transform_detections(chunk);

    // Feed all cameras as a batch — MOT performs Hungarian matching across cameras,
    // deduplicates objects seen by multiple cameras, and runs Kalman filter update.
    // When no detections are present, track() still advances the Kalman filter and
    // increments non-measurement counters so tracks can age and expire.
    tracker_.track(std::move(objects_per_camera), timestamp, rv::tracking::DistanceType::Euclidean,
                   5.0);

    // Get reliable tracks and map RobotVision int IDs to UUID strings
    auto rv_tracks = tracker_.getReliableTracks();
    auto tracks = convert_tracks(rv_tracks, chunk.category);

    LOG_DEBUG("Processed chunk for {}/{}: {} detections -> {} reliable tracks", scope_.scene_id,
              scope_.category,
              std::accumulate(chunk.camera_batches.begin(), chunk.camera_batches.end(), 0,
                              [](int sum, const auto& b) { return sum + b.detections.size(); }),
              tracks.size());

    return tracks;
}

} // namespace tracker
