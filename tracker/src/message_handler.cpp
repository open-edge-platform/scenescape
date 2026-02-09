// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "message_handler.hpp"
#include "logger.hpp"
#include "topic_utils.hpp"

#include <chrono>
#include <ctime>
#include <format>
#include <fstream>
#include <iomanip>
#include <string_view>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/pointer.h>
#include <rapidjson/schema.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker {

namespace {

// Schema file names
constexpr const char* CAMERA_SCHEMA_FILE = "camera-data.schema.json";
constexpr const char* SCENE_SCHEMA_FILE = "scene-data.schema.json";

// Static JSON Pointers for thread-safe, zero-overhead field extraction (RFC 6901)
// These are initialized once at program startup, avoiding per-call path parsing
static const rapidjson::Pointer PTR_ID("/id");
static const rapidjson::Pointer PTR_TIMESTAMP("/timestamp");
static const rapidjson::Pointer PTR_OBJECTS("/objects");
static const rapidjson::Pointer PTR_BBOX("/bounding_box_px");
static const rapidjson::Pointer PTR_BBOX_X("/bounding_box_px/x");
static const rapidjson::Pointer PTR_BBOX_Y("/bounding_box_px/y");
static const rapidjson::Pointer PTR_BBOX_WIDTH("/bounding_box_px/width");
static const rapidjson::Pointer PTR_BBOX_HEIGHT("/bounding_box_px/height");

} // namespace

MessageHandler::MessageHandler(std::shared_ptr<IMqttClient> mqtt_client,
                               const SceneRegistry& scene_registry, bool schema_validation,
                               const std::filesystem::path& schema_dir)
    : mqtt_client_(std::move(mqtt_client)), scene_registry_(scene_registry),
      schema_validation_(schema_validation) {
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
    // Set up message callback
    mqtt_client_->setMessageCallback([this](const std::string& topic, const std::string& payload) {
        handleCameraMessage(topic, payload);
    });

    // Subscribe to each registered camera's topic
    auto camera_ids = scene_registry_.get_all_camera_ids();
    if (camera_ids.empty()) {
        LOG_WARN_ENTRY(
            LogEntry("No cameras registered - not subscribing to any topics").component("mqtt"));
        return;
    }

    // Subscribe to all camera topics (validate UIDs to prevent MQTT topic injection)
    for (const auto& camera_id : camera_ids) {
        if (!isValidTopicSegment(camera_id)) {
            LOG_ERROR_ENTRY(
                LogEntry("Camera ID contains invalid characters for MQTT topic, skipping")
                    .component("mqtt")
                    .domain({.camera_id = camera_id})
                    .error({.type = "validation_error",
                            .message =
                                "UID must contain only alphanumeric, hyphen, underscore, dot"}));
            continue;
        }
        auto topic = std::format(TOPIC_CAMERA_SUBSCRIBE_PATTERN, camera_id);
        mqtt_client_->subscribe(topic);
    }

    // Log subscription summary (individual topics logged at DEBUG in MqttClient)
    LOG_INFO_ENTRY(LogEntry("Queued camera subscriptions")
                       .component("mqtt")
                       .operation(std::format("{} cameras", camera_ids.size())));
}

void MessageHandler::stop() {
    LOG_INFO("MessageHandler stopping, received: {}, published: {}, rejected: {}",
             received_count_.load(), published_count_.load(), rejected_count_.load());

    // Unsubscribe from all camera topics (skip invalid UIDs - same validation as start())
    auto camera_ids = scene_registry_.get_all_camera_ids();
    for (const auto& camera_id : camera_ids) {
        if (!isValidTopicSegment(camera_id)) {
            continue; // Already logged at start(), no need to log again
        }
        auto topic = std::format(TOPIC_CAMERA_SUBSCRIBE_PATTERN, camera_id);
        mqtt_client_->unsubscribe(topic);
    }
    mqtt_client_->setMessageCallback(nullptr);
}

void MessageHandler::handleCameraMessage(const std::string& topic, const std::string& payload) {
    received_count_++;

    std::string_view camera_id_view = extractCameraId(topic);
    if (camera_id_view.empty()) {
        LOG_WARN("Failed to extract camera_id from topic: {}", topic);
        rejected_count_++;
        return;
    }
    std::string camera_id{camera_id_view}; // Single allocation for valid IDs only

    LOG_DEBUG_ENTRY(LogEntry("Received detection")
                        .component("message_handler")
                        .domain({.camera_id = camera_id}));

    // Parse and optionally validate the camera message
    auto message = parseCameraMessage(payload);
    if (!message) {
        LOG_WARN_ENTRY(LogEntry("Failed to parse camera message")
                           .component("message_handler")
                           .domain({.camera_id = camera_id})
                           .error({.type = "parse_error",
                                   .message = "Invalid JSON or schema validation failed"}));
        rejected_count_++;
        return;
    }

    // Log parsed message details (only compute total_detections if debug logging is enabled)
    if (Logger::should_log_debug()) {
        size_t total_detections = 0;
        for (const auto& [category, detections] : message->objects) {
            total_detections += detections.size();
        }
        LOG_DEBUG("Parsed message: camera={}, timestamp={}, detections={}", message->id,
                  message->timestamp, total_detections);
    }
    LOG_DEBUG_ENTRY(LogEntry("Parsed camera message")
                        .component("message_handler")
                        .domain({.camera_id = message->id}));

    // Look up scene for this camera
    const Scene* scene = scene_registry_.find_scene_for_camera(camera_id);
    if (!scene) {
        LOG_WARN_ENTRY(
            LogEntry("Unknown camera not registered to any scene, dropping message")
                .component("message_handler")
                .domain({.camera_id = camera_id})
                .error({.type = "routing_error", .message = "Camera not in scene registry"}));
        rejected_count_++;
        return;
    }

    // Build and publish scene message for each category
    for (const auto& [category, detections] : message->objects) {
        // Validate category on first use (cached to avoid per-frame overhead)
        // Minimal critical section: only lock during cache access, not during publish
        {
            std::lock_guard<std::mutex> lock(categories_mutex_);
            auto [it, is_new] = validated_categories_.insert(category);
            if (is_new && !isValidTopicSegment(category)) {
                validated_categories_.erase(it);
                LOG_ERROR_ENTRY(
                    LogEntry("Category contains invalid characters for MQTT topic, skipping")
                        .component("message_handler")
                        .domain({.scene_id = scene->uid, .object_category = category})
                        .error({.type = "validation_error",
                                .message = "Category must contain only alphanumeric, hyphen, "
                                           "underscore, dot"}));
                continue;
            }
        } // Lock released before expensive operations

        std::string scene_message = buildDummySceneMessage(*scene, message->timestamp);

        // Format output topic: scenescape/data/scene/{scene_id}/{category}
        auto output_topic = std::format(TOPIC_SCENE_DATA_PATTERN, scene->uid, category);

        mqtt_client_->publish(output_topic, scene_message);
        published_count_++;

        LOG_DEBUG_ENTRY(LogEntry("Published track")
                            .component("message_handler")
                            .mqtt({.topic = output_topic, .direction = "publish"})
                            .domain({.scene_id = scene->uid, .object_category = category}));
    }
}

std::string_view MessageHandler::extractCameraId(const std::string& topic) {
    // Topic format: scenescape/data/camera/{camera_id}
    constexpr size_t prefix_len = std::char_traits<char>::length(TOPIC_CAMERA_PREFIX);

    if (topic.size() <= prefix_len) {
        return "";
    }

    if (topic.compare(0, prefix_len, TOPIC_CAMERA_PREFIX) != 0) {
        return "";
    }

    return std::string_view{topic}.substr(prefix_len);
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

    // Extract required fields using JSON Pointers (thread-safe static const pointers)
    CameraMessage message;

    const auto* id_val = PTR_ID.Get(doc);
    if (!id_val || !id_val->IsString()) {
        LOG_WARN("Missing or invalid '/id' field in camera message");
        return std::nullopt;
    }
    message.id = id_val->GetString();

    const auto* timestamp_val = PTR_TIMESTAMP.Get(doc);
    if (!timestamp_val || !timestamp_val->IsString()) {
        LOG_WARN("Missing or invalid '/timestamp' field in camera message");
        return std::nullopt;
    }
    message.timestamp = timestamp_val->GetString();

    const auto* objects_val = PTR_OBJECTS.Get(doc);
    if (!objects_val || !objects_val->IsObject()) {
        LOG_WARN("Missing or invalid '/objects' field in camera message");
        return std::nullopt;
    }

    // Parse objects by category
    for (auto it = objects_val->MemberBegin(); it != objects_val->MemberEnd(); ++it) {
        std::string category = it->name.GetString();

        if (!it->value.IsArray()) {
            LOG_WARN("Invalid detections array for category: {}", category);
            continue;
        }

        const auto& det_array = it->value.GetArray();
        std::vector<Detection> detections;
        detections.reserve(det_array.Size());
        for (const auto& det : det_array) {
            if (!det.IsObject()) {
                continue;
            }

            Detection detection;

            // Optional id field - use direct access since it's a single optional field
            if (det.HasMember("id") && det["id"].IsInt()) {
                detection.id = det["id"].GetInt();
            }

            // Required bounding_box_px - use JSON Pointers for nested field extraction
            const auto* bbox_x = PTR_BBOX_X.Get(det);
            const auto* bbox_y = PTR_BBOX_Y.Get(det);
            const auto* bbox_width = PTR_BBOX_WIDTH.Get(det);
            const auto* bbox_height = PTR_BBOX_HEIGHT.Get(det);

            if (!bbox_x || !bbox_y || !bbox_width || !bbox_height) {
                LOG_WARN("Missing bounding_box_px fields in detection");
                continue;
            }
            // Note: Type checking (IsNumber) omitted - schema validation ensures correct types

            detection.bounding_box_px.x = bbox_x->GetDouble();
            detection.bounding_box_px.y = bbox_y->GetDouble();
            detection.bounding_box_px.width = bbox_width->GetDouble();
            detection.bounding_box_px.height = bbox_height->GetDouble();

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
        rapidjson::StringBuffer schema_sb;
        rapidjson::StringBuffer doc_sb;
        validator.GetInvalidSchemaPointer().StringifyUriFragment(schema_sb);
        validator.GetInvalidDocumentPointer().StringifyUriFragment(doc_sb);
        LOG_WARN(
            "Schema validation failed: document path '{}' violated schema at '{}', keyword: {}",
            doc_sb.GetString(), schema_sb.GetString(), validator.GetInvalidSchemaKeyword());
        return false;
    }
    return true;
}

std::string MessageHandler::buildDummySceneMessage(const Scene& scene,
                                                   const std::string& timestamp) {
    // Build JSON using rapidjson for type safety and schema compliance
    rapidjson::Document doc;
    doc.SetObject();
    auto& allocator = doc.GetAllocator();

    // Add top-level fields
    doc.AddMember("id", rapidjson::Value(scene.uid.c_str(), allocator), allocator);
    doc.AddMember("name", rapidjson::Value(scene.name.c_str(), allocator), allocator);
    doc.AddMember("timestamp", rapidjson::Value(timestamp.c_str(), allocator), allocator);

    // Build objects array with a single dummy track
    rapidjson::Value objects(rapidjson::kArrayType);

    rapidjson::Value track(rapidjson::kObjectType);
    track.AddMember("id", "dummy-track-001", allocator);
    track.AddMember("category", rapidjson::Value(DEFAULT_THING_TYPE, allocator), allocator);

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

    // Note: Output schema validation is done in unit tests, not at runtime

    // Serialize to string
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    doc.Accept(writer);

    return buffer.GetString();
}

} // namespace tracker
