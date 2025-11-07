#pragma once

#include "mqtt_msg.h"
#include <chrono>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

/**
 * Thread-safe buffer for time chunking detection messages.
 * Stores latest detection per camera (overwrites previous frames).
 */
class TimeChunkBuffer {
public:
    TimeChunkBuffer() = default;

    // Add detection to buffer (overwrites previous frame from same camera)
    void add(const CameraDetectionMsg& msg);

    // Pop all buffered detections and clear buffer
    // Returns detections sorted by timestamp (earliest first)
    std::vector<CameraDetectionMsg> pop_all();

    // Get current buffer size
    size_t size() const;

private:
    std::unordered_map<std::string, CameraDetectionMsg> buffer_; // camera_id → detection
    mutable std::mutex mutex_;
};
