// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "mqtt_client.hpp"
#include "scene_registry.hpp"
#include "time_chunk_buffer.hpp"
#include "tracking_types.hpp"

#include <atomic>
#include <chrono>
#include <filesystem>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

#include <rapidjson/document.h>
#include <rapidjson/schema.h>

namespace tracker {

/**
 * @brief Parsed camera detection message.
 */
struct CameraMessage {
    std::string id;
    std::string timestamp;
    std::map<std::string, std::vector<Detection>> objects; // category -> detections
};

/**
 * @brief Handles MQTT message routing for the tracker service.
 *
 * Subscribes to camera detection topics and publishes track data.
 * Currently outputs dummy fixed data for MQTT infrastructure validation.
 *
 * JSON Parsing Notes:
 * - Uses rapidjson for simplicity and schema validation support.
 * - simdjson could be used as a future optimization if profiling shows
 *   MQTT message parsing is a performance bottleneck. Until then, we
 *   prefer simplicity and built-in schema validation with rapidjson.
 */
class MessageHandler {
public:
    /// Topic prefix for camera detections (used to build per-camera subscriptions)
    static constexpr const char* TOPIC_CAMERA_PREFIX = "scenescape/data/camera/";

    /// Topic pattern for camera subscriptions (format with camera_id)
    static constexpr const char* TOPIC_CAMERA_SUBSCRIBE_PATTERN = "scenescape/data/camera/{}";

    /// Topic pattern for scene output (format with scene_id and thing_type)
    static constexpr const char* TOPIC_SCENE_DATA_PATTERN = "scenescape/data/scene/{}/{}";

    /// Default thing type for output (category from detection)
    static constexpr const char* DEFAULT_THING_TYPE = "thing";

    /**
     * @brief Construct message handler with MQTT client, scene registry, and buffer.
     *
     * @param mqtt_client Shared pointer to MQTT client interface
     * @param scene_registry Reference to scene registry for camera-to-scene lookup
     * @param buffer Reference to time chunk buffer for async processing
     * @param tracking_config Tracking configuration for lag detection
     * @param schema_validation Enable JSON schema validation for messages
     * @param schema_dir Directory containing schema files (for validation)
     */
    explicit MessageHandler(std::shared_ptr<IMqttClient> mqtt_client,
                            const SceneRegistry& scene_registry, TimeChunkBuffer& buffer,
                            const TrackingConfig& tracking_config, bool schema_validation = true,
                            const std::filesystem::path& schema_dir = "/scenescape/schema");

    /**
     * @brief Start message handling (subscribe to topics).
     */
    void start();

    /**
     * @brief Stop message handling.
     */
    void stop();

    /**
     * @brief Get count of messages received.
     */
    [[nodiscard]] int getReceivedCount() const { return received_count_; }

    /**
     * @brief Get count of messages buffered for processing.
     */
    [[nodiscard]] int getBufferedCount() const { return buffered_count_; }

    /**
     * @brief Get count of invalid messages rejected.
     */
    [[nodiscard]] int getRejectedCount() const { return rejected_count_; }

    /**
     * @brief Get count of messages dropped due to lag.
     */
    [[nodiscard]] int getLaggedCount() const { return lagged_count_; }

private:
    /**
     * @brief Handle incoming camera detection message.
     *
     * @param topic MQTT topic (scenescape/data/camera/{camera_id})
     * @param payload JSON message payload
     */
    void handleCameraMessage(const std::string& topic, const std::string& payload);

    /**
     * @brief Extract camera_id from topic.
     *
     * @param topic Full topic string
     * @return Camera ID view or empty view if parsing fails
     */
    static std::string_view extractCameraId(const std::string& topic);

    /**
     * @brief Parse camera message from JSON payload.
     *
     * @param payload JSON payload
     * @return Parsed message or nullopt if parsing fails
     */
    std::optional<CameraMessage> parseCameraMessage(const std::string& payload);

    /**
     * @brief Check if message timestamp is too old (lagged).
     *
     * @param timestamp_iso ISO 8601 timestamp from message
     * @return true if message should be dropped due to lag
     */
    bool isMessageLagged(const std::string& timestamp_iso) const;

    /**
     * @brief Parse ISO 8601 timestamp to time_point.
     *
     * @param timestamp_iso ISO 8601 timestamp string
     * @return Parsed time_point or nullopt if parsing fails
     */
    static std::optional<std::chrono::system_clock::time_point>
    parseTimestamp(const std::string& timestamp_iso);

    /**
     * @brief Validate JSON against a schema.
     *
     * @param doc JSON document to validate
     * @param schema Schema to validate against (must not be null)
     * @return true if valid, false otherwise
     */
    bool validateJson(const rapidjson::Document& doc,
                      const rapidjson::SchemaDocument* schema) const;

    /**
     * @brief Load JSON schema from file.
     *
     * @param schema_path Path to schema file
     * @return Loaded schema or nullptr if loading fails
     */
    static std::unique_ptr<rapidjson::SchemaDocument>
    loadSchema(const std::filesystem::path& schema_path);

    std::shared_ptr<IMqttClient> mqtt_client_;
    const SceneRegistry& scene_registry_;
    TimeChunkBuffer& buffer_;
    TrackingConfig tracking_config_;
    bool schema_validation_;
    std::unique_ptr<rapidjson::SchemaDocument> camera_schema_;
    std::unique_ptr<rapidjson::SchemaDocument> scene_schema_;

    std::atomic<int> received_count_{0};
    std::atomic<int> buffered_count_{0};
    std::atomic<int> rejected_count_{0};
    std::atomic<int> lagged_count_{0};

    /// Cache of validated category names (validated once on first use)
    /// Protected by categories_mutex_ for thread-safe access from MQTT callback
    mutable std::mutex categories_mutex_;
    std::unordered_set<std::string> validated_categories_;
};

} // namespace tracker
