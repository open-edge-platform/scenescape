// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "mqtt_client.hpp"
#include "tracking_types.hpp"

#include <atomic>
#include <memory>
#include <string>

namespace tracker {

/**
 * @brief Publishes tracked objects to MQTT.
 *
 * Serializes Track objects to JSON conforming to scene-data.schema.json
 * and publishes to scenescape/data/scene/{scene_id}/{category}.
 *
 * Thread-safety: Thread-safe. MQTT client handles async I/O internally.
 */
class TrackPublisher {
public:
    /// Topic pattern for scene output (format: scene_id, category)
    static constexpr const char* TOPIC_PATTERN = "scenescape/data/scene/{}/{}";

    /**
     * @brief Construct publisher with MQTT client.
     *
     * @param mqtt_client Shared pointer to MQTT client
     */
    explicit TrackPublisher(std::shared_ptr<IMqttClient> mqtt_client);

    /**
     * @brief Publish tracks for a scene/category.
     *
     * @param scene_id Scene identifier (UUID)
     * @param scene_name Human-readable scene name
     * @param category Object category
     * @param timestamp ISO 8601 timestamp
     * @param tracks Vector of tracked objects
     */
    void publish(const std::string& scene_id, const std::string& scene_name,
                 const std::string& category, const std::string& timestamp,
                 const std::vector<Track>& tracks);

    /**
     * @brief Get count of messages published.
     */
    [[nodiscard]] int published_count() const { return published_count_.load(); }

private:
    /**
     * @brief Serialize tracks to JSON.
     *
     * @param scene_id Scene identifier
     * @param scene_name Scene name
     * @param timestamp ISO 8601 timestamp
     * @param tracks Tracks to serialize
     * @return JSON string
     */
    std::string serialize(const std::string& scene_id, const std::string& scene_name,
                          const std::string& timestamp, const std::vector<Track>& tracks);

    /**
     * @brief Build output topic.
     *
     * @param scene_id Scene identifier
     * @param category Object category
     * @return Topic string
     */
    static std::string build_topic(const std::string& scene_id, const std::string& category);

    std::shared_ptr<IMqttClient> mqtt_client_;
    std::atomic<int> published_count_{0};
};

} // namespace tracker
