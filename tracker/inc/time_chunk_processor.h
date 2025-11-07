#pragma once

#include "rv/tracking/TrackedObject.hpp"
#include "time_chunk_buffer.h"
#include "tracker.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <string>
#include <thread>
#include <vector>

/**
 * Callback function type for processing tracked objects.
 * Parameters: camera_id, tracks, timestamp
 */
using ProcessCallback = std::function<void(const std::string& camera_id,
                                           const std::vector<rv::tracking::TrackedObject>& tracks,
                                           std::chrono::system_clock::time_point timestamp)>;

/**
 * Timer thread that processes buffered detections at fixed intervals.
 * Implements back-pressure handling by dropping messages when tracker is busy.
 */
class TimeChunkProcessor {
public:
    TimeChunkProcessor(Tracker* tracker, const std::string& scene_id, int interval_ms,
                       ProcessCallback callback);
    ~TimeChunkProcessor();

    // Disable copy
    TimeChunkProcessor(const TimeChunkProcessor&) = delete;
    TimeChunkProcessor& operator=(const TimeChunkProcessor&) = delete;

    // Start worker thread (no internal timer)
    void start();

    // Stop worker thread (graceful shutdown)
    void stop();

    // Add detection to buffer (called from MQTT thread)
    void add_detection(const CameraDetectionMsg& msg);

    // Called by the global scheduler at each interval
    // Returns true if a batch was enqueued for processing
    bool try_enqueue_tick();

private:
    void worker_loop();

    TimeChunkBuffer buffer_;
    Tracker* tracker_;
    std::string scene_id_;
    std::chrono::milliseconds interval_;
    ProcessCallback callback_;
    std::thread worker_thread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> worker_processing_{false};
    std::mutex work_mtx_;
    std::condition_variable work_cv_;
    bool has_task_{false};
    std::vector<CameraDetectionMsg> pending_batch_;
};
