// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "message_handler.hpp"
#include "logger.hpp"

#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <sstream>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/schema.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker {

namespace {

// Topic prefix for camera data
constexpr const char* CAMERA_TOPIC_PREFIX = "scenescape/data/camera/";
constexpr size_t CAMERA_TOPIC_PREFIX_LEN = 23; // strlen("scenescape/data/camera/")

// Schema file names
constexpr const char* CAMERA_SCHEMA_FILE = "camera-data.schema.json";
constexpr const char* SCENE_SCHEMA_FILE = "scene-data.schema.json";

} // namespace

MessageHandler::MessageHandler(std::shared_ptr<IMqttClient> mqtt_client, bool schema_validation,
                               const std::filesystem::path& schema_dir)
    : mqtt_client_(std::move(mqtt_client)), schema_validation_(schema_validation) {
    if (schema_validation_) {
        auto camera_schema_path = schema_dir / CAMERA_SCHEMA_FILE;
        auto scene_schema_path = schema_dir / SCENE_SCHEMA_FILE;

        camera_schema_ = loadSchema(camera_schema_path);
        scene_schema_ = loadSchema(scene_schema_path);

        if (!camera_schema_) {
            LOG_WARN("Failed to load camera schema from {}, validation disabled for input",
                     camera_schema_path.string());
        }
        if (!scene_schema_) {
            LOG_WARN("Failed to load scene schema from {}, validation disabled for output",
                     scene_schema_path.string());
        }

        if (camera_schema_ && scene_schema_) {
            LOG_INFO("Schema validation enabled for MQTT messages");
        }
    } else {
        LOG_INFO("Schema validation disabled for MQTT messages");
    }
}

std::unique_ptr<rapidjson::SchemaDocument>
MessageHandler::loadSchema(const std::filesystem::path& schema_path) {
    std::ifstream ifs(schema_path);
    if (!ifs.is_open()) {
        LOG_ERROR("Failed to open schema file: {}", schema_path.string());
        return nullptr;
    }

    rapidjson::IStreamWrapper isw(ifs);
    rapidjson::Document schema_doc;
    schema_doc.ParseStream(isw);

    if (schema_doc.HasParseError()) {
        LOG_ERROR("Failed to parse schema file: {} at offset {}", schema_path.string(),
                  schema_doc.GetErrorOffset());
        return nullptr;
    }

    return std::make_unique<rapidjson::SchemaDocument>(schema_doc);
}

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
    LOG_INFO("MessageHandler stopping (received: {}, published: {}, rejected: {})",
             received_count_.load(), published_count_.load(), rejected_count_.load());

    mqtt_client_->setMessageCallback(nullptr);
}

void MessageHandler::handleCameraMessage(const std::string& topic, const std::string& payload) {
    received_count_++;

    std::string camera_id = extractCameraId(topic);
    if (camera_id.empty()) {
        LOG_WARN("Failed to extract camera_id from topic: {}", topic);
        rejected_count_++;
        return;
    }

    LOG_DEBUG("Received detection from camera: {} ({} bytes)", camera_id, payload.size());

    // Parse and optionally validate the camera message
    auto message = parseCameraMessage(payload);
    if (!message) {
        LOG_WARN("Failed to parse camera message from {}", camera_id);
        rejected_count_++;
        return;
    }

    // Log parsed message details
    size_t total_detections = 0;
    for (const auto& [category, detections] : message->objects) {
        total_detections += detections.size();
    }
    LOG_DEBUG("Parsed message: camera={}, timestamp={}, detections={}", message->id,
              message->timestamp, total_detections);

    // Build and publish dummy scene message
    std::string scene_message = buildDummySceneMessage(message->timestamp);

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

std::optional<CameraMessage> MessageHandler::parseCameraMessage(const std::string& payload) {
    rapidjson::Document doc;
    doc.Parse(payload.c_str());

    if (doc.HasParseError()) {
        LOG_WARN("JSON parse error at offset {}: error code {}", doc.GetErrorOffset(),
                 static_cast<int>(doc.GetParseError()));
        return std::nullopt;
    }

    // Validate against schema if enabled
    if (schema_validation_ && camera_schema_) {
        if (!validateJson(doc, camera_schema_.get())) {
            return std::nullopt;
        }
    }

    // Extract required fields
    CameraMessage message;

    if (!doc.HasMember("id") || !doc["id"].IsString()) {
        LOG_WARN("Missing or invalid 'id' field in camera message");
        return std::nullopt;
    }
    message.id = doc["id"].GetString();

    if (!doc.HasMember("timestamp") || !doc["timestamp"].IsString()) {
        LOG_WARN("Missing or invalid 'timestamp' field in camera message");
        return std::nullopt;
    }
    message.timestamp = doc["timestamp"].GetString();

    if (!doc.HasMember("objects") || !doc["objects"].IsObject()) {
        LOG_WARN("Missing or invalid 'objects' field in camera message");
        return std::nullopt;
    }

    // Parse objects by category
    const auto& objects = doc["objects"];
    for (auto it = objects.MemberBegin(); it != objects.MemberEnd(); ++it) {
        std::string category = it->name.GetString();

        if (!it->value.IsArray()) {
            LOG_WARN("Invalid detections array for category: {}", category);
            continue;
        }

        std::vector<Detection> detections;
        for (const auto& det : it->value.GetArray()) {
            if (!det.IsObject()) {
                continue;
            }

            Detection detection;

            // Optional id field
            if (det.HasMember("id") && det["id"].IsInt()) {
                detection.id = det["id"].GetInt();
            }

            // Required bounding_box_px
            if (!det.HasMember("bounding_box_px") || !det["bounding_box_px"].IsObject()) {
                LOG_WARN("Missing bounding_box_px in detection");
                continue;
            }

            const auto& bbox = det["bounding_box_px"];
            if (!bbox.HasMember("x") || !bbox.HasMember("y") || !bbox.HasMember("width") ||
                !bbox.HasMember("height")) {
                LOG_WARN("Incomplete bounding_box_px in detection");
                continue;
            }

            detection.bounding_box_px.x = bbox["x"].GetDouble();
            detection.bounding_box_px.y = bbox["y"].GetDouble();
            detection.bounding_box_px.width = bbox["width"].GetDouble();
            detection.bounding_box_px.height = bbox["height"].GetDouble();

            detections.push_back(detection);
        }

        if (!detections.empty()) {
            message.objects[category] = std::move(detections);
        }
    }

    return message;
}

bool MessageHandler::validateJson(const rapidjson::Document& doc,
                                  const rapidjson::SchemaDocument* schema) const {
    rapidjson::SchemaValidator validator(*schema);
    if (!doc.Accept(validator)) {
        rapidjson::StringBuffer sb;
        validator.GetInvalidSchemaPointer().StringifyUriFragment(sb);
        LOG_WARN("Schema validation failed at: {}, keyword: {}", sb.GetString(),
                 validator.GetInvalidSchemaKeyword());
        return false;
    }
    return true;
}

std::string MessageHandler::buildDummySceneMessage(const std::string& timestamp) {
    // Build JSON using rapidjson for type safety and schema compliance
    rapidjson::Document doc;
    doc.SetObject();
    auto& allocator = doc.GetAllocator();

    // Add top-level fields
    doc.AddMember("id", rapidjson::Value(DUMMY_SCENE_ID, allocator), allocator);
    doc.AddMember("name", rapidjson::Value(DUMMY_SCENE_NAME, allocator), allocator);
    doc.AddMember("timestamp", rapidjson::Value(timestamp.c_str(), allocator), allocator);

    // Build objects array with a single dummy track
    rapidjson::Value objects(rapidjson::kArrayType);

    rapidjson::Value track(rapidjson::kObjectType);
    track.AddMember("id", "dummy-track-001", allocator);
    track.AddMember("category", rapidjson::Value(DUMMY_THING_TYPE, allocator), allocator);

    // Translation [x, y, z]
    rapidjson::Value translation(rapidjson::kArrayType);
    translation.PushBack(1.0, allocator);
    translation.PushBack(2.0, allocator);
    translation.PushBack(0.0, allocator);
    track.AddMember("translation", translation, allocator);

    // Velocity [vx, vy, vz]
    rapidjson::Value velocity(rapidjson::kArrayType);
    velocity.PushBack(0.1, allocator);
    velocity.PushBack(0.2, allocator);
    velocity.PushBack(0.0, allocator);
    track.AddMember("velocity", velocity, allocator);

    // Size [length, width, height]
    rapidjson::Value size(rapidjson::kArrayType);
    size.PushBack(0.5, allocator);
    size.PushBack(0.5, allocator);
    size.PushBack(1.8, allocator);
    track.AddMember("size", size, allocator);

    // Rotation quaternion [x, y, z, w]
    rapidjson::Value rotation(rapidjson::kArrayType);
    rotation.PushBack(0, allocator);
    rotation.PushBack(0, allocator);
    rotation.PushBack(0, allocator);
    rotation.PushBack(1, allocator);
    track.AddMember("rotation", rotation, allocator);

    objects.PushBack(track, allocator);
    doc.AddMember("objects", objects, allocator);

    // Validate output against schema if enabled
    if (schema_validation_ && scene_schema_) {
        if (!validateJson(doc, scene_schema_.get())) {
            LOG_ERROR("Output message failed schema validation - this is a bug!");
        }
    }

    // Serialize to string
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    doc.Accept(writer);

    return buffer.GetString();
}

} // namespace tracker
