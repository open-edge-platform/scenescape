// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "observability_context.hpp"

#include <array>
#include <chrono>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include <opencv2/core.hpp>

namespace tracker {

/**
 * @brief Single detection from camera frame.
 *
 * Represents one detected object before tracking. A detection has either a
 * pixel-space bounding box or a sensor-frame translation and size.
 */
struct Detection {
    std::optional<int32_t> id; ///< Frame-local detection ID (optional)
    cv::Rect2f bounding_box_px;
    std::optional<std::array<double, 3>> translation; ///< Sensor-frame position in metres
    std::optional<std::array<double, 3>> size;        ///< Object dimensions [x, y, z] in metres
    std::optional<std::array<double, 4>> rotation;    ///< Sensor-frame quaternion [x, y, z, w]
    std::string metadata_json; ///< Semantic metadata, excluding ReID (empty if absent)
    std::string reid_json;     ///< ReID payload, normalized to an object at the parse boundary
    std::optional<double> reid_confidence;
    std::optional<double>
        confidence; ///< Detection confidence score in [0, 1] (absent if not provided)
};

/**
 * @brief Parsed camera detection message.
 */
struct CameraMessage {
    std::string id;
    std::string timestamp;
    std::map<std::string, std::vector<Detection>> objects; // category -> detections
};

namespace ptz {
struct PoseSnapshot;
} // namespace ptz

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
    ObservabilityContext obs_ctx; ///< Pipeline observability context

    /// PoseContext that admitted this PTZ batch; projection uses it instead of the static
    /// extrinsics. Null for static cameras, shadow mode, and gated batches.
    std::shared_ptr<const ptz::PoseSnapshot> ptz_pose;
    /// PTZ batch (enforcing mode): kept alongside earlier same-camera batches with distinct
    /// timestamps in one chunk, because each carries its own dwell decision and pose.
    bool ptz_preserve = false;
    /// Detection-less heartbeat for a rejected PTZ batch: ages tracks, never displaces data.
    bool ptz_gated = false;
};

/**
 * @brief Buffered batches of one camera within a scope for the current chunk.
 *
 * Static cameras keep only `latest` (keep-latest semantics). PTZ batches with distinct
 * timestamps move the previous batch into `earlier` (bounded), so a later dwell decision
 * can never be applied to another batch's detections. `earlier` stays empty (no
 * allocation) for static cameras.
 */
struct CameraSlot {
    DetectionBatch latest;
    std::vector<DetectionBatch> earlier;
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
    ObservabilityContext obs_ctx;               ///< Earliest batch's observability context

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
    std::string
        metadata_json; ///< Raw JSON string of the detection's metadata object (empty if absent)
    std::optional<double>
        confidence; ///< Detection confidence score in [0, 1] (absent if not available)
    std::string reid_sighting_json; ///< Current-chunk detection crop and embedding, if any
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
using CameraMap = std::unordered_map<std::string, CameraSlot>; ///< camera_id → batches
using BufferMap =
    std::unordered_map<TrackingScope, CameraMap, TrackingScopeHash>; ///< scope → cameras

} // namespace tracker
