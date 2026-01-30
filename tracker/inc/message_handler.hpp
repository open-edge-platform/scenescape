// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "mqtt_client.hpp"

#include <atomic>
#include <filesystem>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <rapidjson/document.h>
#include <rapidjson/schema.h>

namespace tracker {

/**
 * @brief Bounding box in pixel coordinates.
 */
struct BoundingBox {
    double x;
    double y;
    double width;
    double height;
};

/**
 * @brief Single detection from camera message.
 */
struct Detection {
    std::optional<int> id;
    BoundingBox bounding_box_px;
};

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
    /// Topic for camera detections (wildcard subscription)
    static constexpr const char* TOPIC_CAMERA_DATA = "scenescape/data/camera/+";

    /// Topic pattern for scene output (format with scene_id and thing_type)
    static constexpr const char* TOPIC_SCENE_DATA_PATTERN = "scenescape/data/scene/{}/{}";

    /// Default scene ID for dummy output
    static constexpr const char* DUMMY_SCENE_ID = "dummy-scene";

    /// Default scene name for dummy output
    static constexpr const char* DUMMY_SCENE_NAME = "Test Scene";

    /// Default thing type for dummy output
    static constexpr const char* DUMMY_THING_TYPE = "thing";

    /**
     * @brief Construct message handler with MQTT client.
     *
     * @param mqtt_client Shared pointer to MQTT client interface
     * @param schema_validation Enable JSON schema validation for messages
     * @param schema_dir Directory containing schema files (for validation)
     */
    explicit MessageHandler(std::shared_ptr<IMqttClient> mqtt_client, bool schema_validation = true,
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
     * @brief Get count of messages published.
     */
    [[nodiscard]] int getPublishedCount() const { return published_count_; }

    /**
     * @brief Get count of invalid messages rejected.
     */
    [[nodiscard]] int getRejectedCount() const { return rejected_count_; }

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
     * @brief Build dummy scene output message using rapidjson.
     *
     * @param timestamp ISO 8601 timestamp from input message
     * @return JSON string conforming to scene-data.schema.json
     */
    std::string buildDummySceneMessage(const std::string& timestamp);

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
    bool schema_validation_;
    std::unique_ptr<rapidjson::SchemaDocument> camera_schema_;
    std::unique_ptr<rapidjson::SchemaDocument> scene_schema_;

    std::atomic<int> received_count_{0};
    std::atomic<int> published_count_{0};
    std::atomic<int> rejected_count_{0};
};

} // namespace tracker
