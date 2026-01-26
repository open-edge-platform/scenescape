// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "message_handler.hpp"
#include "logger.hpp"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

#include <simdjson.h>

namespace tracker {

namespace {

// Topic prefix for camera data
constexpr const char* CAMERA_TOPIC_PREFIX = "scenescape/data/camera/";
constexpr size_t CAMERA_TOPIC_PREFIX_LEN = 23; // strlen("scenescape/data/camera/")

} // namespace

MessageHandler::MessageHandler(std::shared_ptr<MqttClient> mqtt_client)
    : mqtt_client_(std::move(mqtt_client)) {}

void MessageHandler::start() {
    LOG_INFO("MessageHandler starting, subscribing to: {}", TOPIC_CAMERA_DATA);

    // Set up message callback
    mqtt_client_->setMessageCallback([this](const std::string& topic, const std::string& payload) {
        handleCameraMessage(topic, payload);
    });

    // Subscribe to camera topics
    mqtt_client_->subscribe(TOPIC_CAMERA_DATA);
}

void MessageHandler::stop() {
    LOG_INFO("MessageHandler stopping (received: {}, published: {})", received_count_.load(),
             published_count_.load());

    mqtt_client_->setMessageCallback(nullptr);
}

void MessageHandler::handleCameraMessage(const std::string& topic, const std::string& payload) {
    received_count_++;

    std::string camera_id = extractCameraId(topic);
    if (camera_id.empty()) {
        LOG_WARN("Failed to extract camera_id from topic: {}", topic);
        return;
    }

    LOG_DEBUG("Received detection from camera: {} ({} bytes)", camera_id, payload.size());

    // Extract timestamp from message or use current time
    std::string timestamp = extractTimestamp(payload);

    // Build and publish dummy scene message
    std::string scene_message = buildDummySceneMessage(timestamp);

    // Format output topic: scenescape/data/scene/{scene_id}/{thing_type}
    std::ostringstream output_topic;
    output_topic << "scenescape/data/scene/" << DUMMY_SCENE_ID << "/" << DUMMY_THING_TYPE;

    mqtt_client_->publish(output_topic.str(), scene_message);
    published_count_++;

    LOG_DEBUG("Published track to: {} ({} bytes)", output_topic.str(), scene_message.size());
}

std::string MessageHandler::extractCameraId(const std::string& topic) {
    // Topic format: scenescape/data/camera/{camera_id}
    if (topic.size() <= CAMERA_TOPIC_PREFIX_LEN) {
        return "";
    }

    if (topic.compare(0, CAMERA_TOPIC_PREFIX_LEN, CAMERA_TOPIC_PREFIX) != 0) {
        return "";
    }

    return topic.substr(CAMERA_TOPIC_PREFIX_LEN);
}

std::string MessageHandler::extractTimestamp(const std::string& payload) {
    try {
        simdjson::ondemand::parser parser;
        simdjson::padded_string json(payload);
        simdjson::ondemand::document doc = parser.iterate(json);

        std::string_view timestamp = doc["timestamp"].get_string();
        return std::string(timestamp);
    } catch (const simdjson::simdjson_error& e) {
        LOG_DEBUG("Failed to extract timestamp, using current time: {}", e.what());
        return getCurrentTimestamp();
    }
}

std::string MessageHandler::getCurrentTimestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t_now = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;

    std::ostringstream oss;
    oss << std::put_time(std::gmtime(&time_t_now), "%Y-%m-%dT%H:%M:%S");
    oss << '.' << std::setfill('0') << std::setw(3) << ms.count() << 'Z';
    return oss.str();
}

std::string MessageHandler::buildDummySceneMessage(const std::string& timestamp) {
    // Build JSON conforming to scene-data.schema.json
    // Using string concatenation for simplicity (no JSON library dependency for output)
    std::ostringstream json;
    json << R"({)" << R"("id":")" << DUMMY_SCENE_ID << R"(",)" << R"("name":")" << DUMMY_SCENE_NAME
         << R"(",)" << R"("timestamp":")" << timestamp << R"(",)" << R"("objects":[)" << R"({)"
         << R"("id":"dummy-track-001",)" << R"("category":")" << DUMMY_THING_TYPE << R"(",)"
         << R"("translation":[1.0,2.0,0.0],)" << R"("velocity":[0.1,0.2,0.0],)"
         << R"("size":[0.5,0.5,1.8],)" << R"("rotation":[0,0,0,1])" << R"(})" << R"(])" << R"(})";
    return json.str();
}

} // namespace tracker
