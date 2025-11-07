#include "time_chunk_buffer.h"
#include <algorithm>

void TimeChunkBuffer::add(const CameraDetectionMsg& msg) {
    std::lock_guard<std::mutex> lock(mutex_);

    // Overwrite previous frame from this camera (performance optimization)
    buffer_[msg.id] = msg;
}

std::vector<CameraDetectionMsg> TimeChunkBuffer::pop_all() {
    std::lock_guard<std::mutex> lock(mutex_);

    std::vector<CameraDetectionMsg> result;
    result.reserve(buffer_.size());

    // Move all buffered detections to result vector
    for (auto& [camera_id, detection] : buffer_) {
        result.push_back(std::move(detection));
    }

    // Clear the buffer
    buffer_.clear();

    // Sort by timestamp (earliest first) to match Controller behavior
    std::sort(result.begin(), result.end(),
              [](const CameraDetectionMsg& a, const CameraDetectionMsg& b) {
                  return a.get_timestamp() < b.get_timestamp();
              });

    return result;
}

size_t TimeChunkBuffer::size() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return buffer_.size();
}
