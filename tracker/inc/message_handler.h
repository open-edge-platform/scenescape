#pragma once

#include "scene_config.h"
#include "mqtt_msg.h"
#include "publisher.h"
#include "time_chunk_processor.h"
#include "tracker.h"
#include <memory>
#include <shared_mutex>
#include <unordered_map>

/**
 * Message Handler for processing MQTT detection messages
 * Encapsulates the logic for handling incoming camera detection messages,
 * coordinating between per-scene tracker instances and publisher components.
 * Supports dynamic reconfiguration via reconstruction.
 */
class MessageHandler {
public:
    /**
     * Constructor - creates per-scene tracker instances
     * @param publisher Reference to the publisher instance
     * @param scene_config Reference to the scene configuration (cameras and scenes)
     * @param time_chunking_fps FPS for time chunking (default 15)
     * @param max_lag_seconds Maximum acceptable message age in seconds (default 1.0)
     */
    MessageHandler(Publisher& publisher, const SceneConfiguration& scene_config,
                   int time_chunking_fps, double max_lag_seconds);

    ~MessageHandler();

    /**
     * Handle incoming camera detection message
     * Validates timestamp, buffers detection for time chunking
     * @param detectionMsg The camera detection message to process
     */
    void handleDetectionMessage(const CameraDetectionMsg& detectionMsg);

private:
    // Helper to get or create tracker for scene+category
    Tracker* get_or_create_tracker(const std::string& scene_id, const std::string& category);

    // Helper to get or create time chunk processor for scene+category
    TimeChunkProcessor* get_or_create_processor(const std::string& scene_id,
                                                const std::string& category);

    // Per-scene, per-category tracker instances (owned)
    // Map structure: scene_id -> category -> Tracker
    std::unordered_map<std::string, std::unordered_map<std::string, std::unique_ptr<Tracker>>>
        scene_trackers_;
    mutable std::shared_mutex trackers_mutex_;

    // Per-scene, per-category time chunk processors (owned)
    // Map structure: scene_id -> category -> TimeChunkProcessor
    std::unordered_map<std::string,
                       std::unordered_map<std::string, std::unique_ptr<TimeChunkProcessor>>>
        time_chunk_processors_;
    mutable std::shared_mutex processors_mutex_;

    // Routing maps
    std::unordered_map<std::string, std::string> camera_to_scene_;
    std::unordered_map<std::string, std::string> scene_to_name_;
    mutable std::shared_mutex routing_mutex_;

    // Configuration data needed for lazy initialization
    std::unordered_map<std::string, std::vector<CameraConfig>> scene_cameras_;
    int time_chunking_fps_;

    Publisher& publisher_;
    double max_lag_seconds_;
};
