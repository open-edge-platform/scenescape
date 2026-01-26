// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "mqtt_client.hpp"

#include <atomic>
#include <memory>
#include <string>

namespace tracker {

/**
 * @brief Handles MQTT message routing for the tracker service.
 *
 * Subscribes to camera detection topics and publishes track data.
 * Currently outputs dummy fixed data for MQTT infrastructure validation.
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
     * @param mqtt_client Shared pointer to MQTT client
     */
    explicit MessageHandler(std::shared_ptr<MqttClient> mqtt_client);

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
     * @return Camera ID or empty string if parsing fails
     */
    static std::string extractCameraId(const std::string& topic);

    /**
     * @brief Build dummy scene output message.
     *
     * @param timestamp ISO 8601 timestamp from input message
     * @return JSON string conforming to scene-data.schema.json
     */
    static std::string buildDummySceneMessage(const std::string& timestamp);

    /**
     * @brief Extract timestamp from camera message.
     *
     * @param payload JSON payload
     * @return Timestamp string or current time if not found
     */
    static std::string extractTimestamp(const std::string& payload);

    /**
     * @brief Get current ISO 8601 timestamp.
     */
    static std::string getCurrentTimestamp();

    std::shared_ptr<MqttClient> mqtt_client_;
    std::atomic<int> received_count_{0};
    std::atomic<int> published_count_{0};
};

} // namespace tracker
