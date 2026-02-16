// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <chrono>
#include <functional>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include <opencv2/core.hpp>

namespace tracker {

/**
 * @brief Single detection from camera frame.
 *
 * Represents one detected object in pixel coordinates before tracking.
 * bounding_box_px uses cv::Rect2f to match OpenCV conventions and avoid
 * manual conversion in the tracking pipeline.
 */
struct Detection {
    std::optional<int32_t> id; ///< Frame-local detection ID (optional)
    cv::Rect2f bounding_box_px;
};

/**
 * @brief Composite key for worker routing.
 *
 * Each scope (scene+category combination) gets its own tracker instance.
 */
struct TrackingScope {
    std::string scene_id;
    std::string category;

    auto operator==(const TrackingScope&) const -> bool = default;
};

/**
 * @brief All detections from a single camera frame.
 *
 * This is the unit stored in TimeChunkBuffer per camera within a scope.
 */
struct DetectionBatch {
    std::string camera_id;
    std::chrono::steady_clock::time_point receive_time;
    std::string timestamp_iso;                       ///< Original ISO 8601 timestamp from message
    std::chrono::system_clock::time_point timestamp; ///< Parsed UTC timestamp
    std::vector<Detection> detections;
};

/**
 * @brief Aggregated batches from multiple cameras within one time interval.
 *
 * Dispatched to TrackingWorker for processing. Camera batches are sorted
 * by timestamp before dispatch.
 */
struct Chunk {
    std::string scene_id;
    std::string category;
    std::chrono::steady_clock::time_point chunk_time;
    std::vector<DetectionBatch> camera_batches; ///< Sorted by timestamp

    /**
     * @brief Check if this is a sentinel chunk (signals shutdown).
     */
    [[nodiscard]] bool is_sentinel() const { return scene_id.empty(); }

    /**
     * @brief Create a sentinel chunk for graceful shutdown.
     */
    static Chunk make_sentinel() { return Chunk{}; }
};

/**
 * @brief Tracked object output in world coordinates.
 *
 * Matches the output schema from scene-data.schema.json.
 */
struct Track {
    std::string id;       ///< Persistent track ID (UUID v4, mapped from RobotVision ID)
    std::string category; ///< Object category (e.g., person, vehicle)
    std::array<double, 3> translation; ///< World position [x, y, z] meters
    std::array<double, 3> velocity;    ///< Velocity [vx, vy, vz] m/s
    std::array<double, 3> size;        ///< Object size [length, width, height] meters
    std::array<double, 4> rotation;    ///< Orientation quaternion [x, y, z, w]
};

/**
 * @brief Output message containing tracked objects for a scene.
 *
 * Published to scenescape/data/scene/{scene_id}/{category}.
 */
struct TrackMessage {
    std::string scene_id;   ///< Scene UUID
    std::string scene_name; ///< Human-readable scene name
    std::string timestamp;  ///< ISO 8601 timestamp
    std::vector<Track> tracks;
};

/**
 * @brief Hash functor for TrackingScope.
 *
 * Defined as a custom functor in tracker namespace rather than specializing
 * std::hash, which is safer and clearer per C++ coding guidelines.
 */
struct TrackingScopeHash {
    auto operator()(const TrackingScope& s) const noexcept -> std::size_t {
        const auto h1 = std::hash<std::string>{}(s.scene_id);
        const auto h2 = std::hash<std::string>{}(s.category);
        // XOR-shift combine (matches implementation.md)
        return h1 ^ (h2 * 0x9e3779b97f4a7c15ULL + (h1 << 6) + (h1 >> 2));
    }
};

// Type aliases for buffer structures
using CameraMap = std::unordered_map<std::string, DetectionBatch>; ///< camera_id → batch
using BufferMap =
    std::unordered_map<TrackingScope, CameraMap, TrackingScopeHash>; ///< scope → cameras

} // namespace tracker
