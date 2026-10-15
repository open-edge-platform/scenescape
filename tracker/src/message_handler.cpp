// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "message_handler.hpp"
#include "logger.hpp"
#include "metrics.hpp"
#include "observability_context.hpp"
#include "time_utils.hpp"
#include "topic_utils.hpp"

#include <algorithm>
#include <chrono>
#include <format>
#include <fstream>
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
constexpr const char* EXTERNAL_SOURCE_SCHEMA_FILE = "external-source.schema.json";
constexpr auto kExternalSourceSweepInterval = std::chrono::seconds(30);

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

template <size_t Size>
std::array<double, Size> parseNumberArray(const rapidjson::Value& value) {
    std::array<double, Size> result{};
    for (rapidjson::SizeType index = 0; index < Size; ++index) {
        result[index] = value[index].GetDouble();
    }
    return result;
}

template <size_t Size>
bool isNumberArray(const rapidjson::Value& value) {
    if (!value.IsArray() || value.Size() != Size) {
        return false;
    }
    return std::all_of(value.Begin(), value.End(),
                       [](const rapidjson::Value& element) { return element.IsNumber(); });
}

std::unordered_map<std::string, std::vector<const Scene*>>
resolveExternalSceneBindings(const ExternalSourcesConfig& external_sources_config,
                             const SceneRegistry& scene_registry) {
    std::unordered_map<std::string, std::vector<const Scene*>> resolved_bindings;
    for (const auto& [publisher_id, scene_ids] : external_sources_config.bindings) {
        auto& scenes = resolved_bindings[publisher_id];
        for (const auto& scene_id : scene_ids) {
            if (const auto* scene = scene_registry.find_scene_by_id(scene_id)) {
                scenes.push_back(scene);
            } else {
                LOG_WARN("External binding scene '{}' not found for publisher '{}'", scene_id,
                         publisher_id);
            }
        }
    }
    return resolved_bindings;
}

} // namespace

MessageHandler::MessageHandler(std::shared_ptr<IMqttClient> mqtt_client,
                               const SceneRegistry& scene_registry, TimeChunkBuffer& buffer,
                               const TrackingConfig& tracking_config, bool schema_validation,
                               const std::filesystem::path& schema_dir, ClockFn clock_fn,
                               ExternalSourcesConfig external_sources_config)
    : mqtt_client_(std::move(mqtt_client)), scene_registry_(scene_registry), buffer_(buffer),
      tracking_config_(tracking_config), schema_validation_(schema_validation),
      external_sources_config_(std::move(external_sources_config)),
      external_scene_bindings_(
          resolveExternalSceneBindings(external_sources_config_, scene_registry_)),
      external_pose_cache_(kDefaultExternalSourceTtlSeconds, kDefaultExternalSourceSweepChunkSize,
                           tracking_config.max_lag_s),
      identity_claim_registry_(kDefaultExternalSourceTtlSeconds,
                               kDefaultExternalSourceSweepChunkSize, tracking_config.max_lag_s),
      clock_fn_(std::move(clock_fn)) {
    if (schema_validation_) {
        auto camera_schema_path = schema_dir / CAMERA_SCHEMA_FILE;
        auto scene_schema_path = schema_dir / SCENE_SCHEMA_FILE;
        auto external_source_schema_path = schema_dir / EXTERNAL_SOURCE_SCHEMA_FILE;

        camera_schema_ = loadSchema(camera_schema_path);
        scene_schema_ = loadSchema(scene_schema_path);
        external_source_schema_ = loadSchema(external_source_schema_path);

        if (!camera_schema_) {
            LOG_WARN("Failed to load camera schema from {}, validation disabled for input",
                     camera_schema_path.string());
        }
        if (!scene_schema_) {
            LOG_WARN("Failed to load scene schema from {}, validation disabled for output",
                     scene_schema_path.string());
        }
        if (!external_source_schema_) {
            LOG_WARN("Failed to load external-source schema from {}, validation disabled for input",
                     external_source_schema_path.string());
        }

        if (camera_schema_ && scene_schema_) {
            LOG_INFO("Schema validation enabled for MQTT messages");
        }
    } else {
        LOG_INFO("Schema validation disabled for MQTT messages");
    }
}

MessageHandler::~MessageHandler() {
    stopExternalSourceSweeper();
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

void MessageHandler::enableDynamicMode(ShutdownCallback callback) {
    dynamic_mode_ = true;
    shutdown_callback_ = std::move(callback);
    LOG_INFO_ENTRY(LogEntry("Dynamic mode enabled - will subscribe to database update topic")
                       .component("mqtt"));
}

void MessageHandler::start() {
    startExternalSourceSweeper();

    // Set up message callback with topic-based routing
    mqtt_client_->setMessageCallback([this](const std::string& topic, const std::string& payload) {
        routeMessage(topic, payload);
    });

    mqtt_client_->subscribe(TOPIC_EXTERNAL_SUBSCRIBE);
    LOG_INFO_ENTRY(LogEntry("Queued external-source subscription")
                       .component("mqtt")
                       .operation(TOPIC_EXTERNAL_SUBSCRIBE));

    // In dynamic mode, subscribe to database update topic for config change notifications
    if (dynamic_mode_) {
        mqtt_client_->subscribe(TOPIC_DATABASE_UPDATE);
        LOG_INFO_ENTRY(LogEntry("Queued database update subscription")
                           .component("mqtt")
                           .operation(TOPIC_DATABASE_UPDATE));
    }

    // Subscribe to each registered camera's topic
    auto camera_ids = scene_registry_.get_all_camera_ids();
    if (camera_ids.empty()) {
        LOG_WARN_ENTRY(
            LogEntry("No cameras registered - not subscribing to camera topics").component("mqtt"));
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
    stopExternalSourceSweeper();

    LOG_INFO("MessageHandler stopping (received: {}, buffered: {}, rejected: {}, lagged: {})",
             received_count_.load(), buffered_count_.load(), rejected_count_.load(),
             lagged_count_.load());

    mqtt_client_->unsubscribe(TOPIC_EXTERNAL_SUBSCRIBE);

    // Unsubscribe from all camera topics (skip invalid UIDs - same validation as start())
    auto camera_ids = scene_registry_.get_all_camera_ids();
    for (const auto& camera_id : camera_ids) {
        if (!isValidTopicSegment(camera_id)) {
            continue; // Already logged at start(), no need to log again
        }
        auto topic = std::format(TOPIC_CAMERA_SUBSCRIBE_PATTERN, camera_id);
        mqtt_client_->unsubscribe(topic);
    }

    // Unsubscribe from database update topic (dynamic mode)
    if (dynamic_mode_) {
        mqtt_client_->unsubscribe(TOPIC_DATABASE_UPDATE);
    }

    mqtt_client_->setMessageCallback(nullptr);
}

void MessageHandler::startExternalSourceSweeper() {
    std::lock_guard lock(external_sweeper_mutex_);
    if (external_sweeper_thread_.joinable()) {
        return;
    }
    external_sweeper_stop_requested_ = false;
    external_sweeper_thread_ = std::thread(&MessageHandler::externalSourceSweepLoop, this);
}

void MessageHandler::stopExternalSourceSweeper() {
    std::thread sweeper;
    {
        std::lock_guard lock(external_sweeper_mutex_);
        external_sweeper_stop_requested_ = true;
        if (external_sweeper_thread_.joinable()) {
            sweeper = std::move(external_sweeper_thread_);
        }
    }
    external_sweeper_cv_.notify_all();
    if (sweeper.joinable()) {
        sweeper.join();
    }
}

void MessageHandler::externalSourceSweepLoop() {
    std::unique_lock lock(external_sweeper_mutex_);
    while (!external_sweeper_stop_requested_) {
        if (external_sweeper_cv_.wait_for(lock, kExternalSourceSweepInterval,
                                          [this] { return external_sweeper_stop_requested_; })) {
            return;
        }
        lock.unlock();
        const auto now = clock_fn_();
        external_pose_cache_.sweepExpired(now);
        identity_claim_registry_.sweepExpired(now);
        lock.lock();
    }
}

void MessageHandler::routeMessage(const std::string& topic, const std::string& payload) {
    if (dynamic_mode_ && topic == TOPIC_DATABASE_UPDATE) {
        handleDatabaseUpdateMessage(topic, payload);
    } else if (topic.starts_with(TOPIC_EXTERNAL_PREFIX)) {
        handleExternalSourceMessage(topic, payload);
    } else if (topic.starts_with(TOPIC_CAMERA_PREFIX)) {
        handleCameraMessage(topic, payload);
    } else {
        LOG_WARN("Rejecting message from unsupported topic: {}", topic);
        rejected_count_++;
    }
}

std::optional<std::pair<std::string, std::string>>
MessageHandler::extractExternalTopic(const std::string& topic) {
    if (!topic.starts_with(TOPIC_EXTERNAL_PREFIX)) {
        return std::nullopt;
    }
    const std::string_view remainder(
        topic.data() + std::char_traits<char>::length(TOPIC_EXTERNAL_PREFIX),
        topic.size() - std::char_traits<char>::length(TOPIC_EXTERNAL_PREFIX));
    const size_t separator = remainder.find('/');
    if (separator == std::string_view::npos || separator == 0 ||
        separator == remainder.size() - 1 ||
        remainder.find('/', separator + 1) != std::string_view::npos) {
        return std::nullopt;
    }
    std::string publisher_id(remainder.substr(0, separator));
    std::string category(remainder.substr(separator + 1));
    if (!isValidTopicSegment(publisher_id) || !isValidTopicSegment(category)) {
        return std::nullopt;
    }
    return std::pair{std::move(publisher_id), std::move(category)};
}

std::optional<ExternalSourceMessage>
MessageHandler::parseExternalSourceMessage(const std::string& payload) {
    rapidjson::Document document;
    document.Parse(payload.c_str());
    if (document.HasParseError() || !document.IsObject() ||
        (schema_validation_ && external_source_schema_ &&
         !validateJson(document, external_source_schema_.get()))) {
        LOG_WARN("Failed to validate external source message against schema -  {}",
                 payload.c_str());
        return std::nullopt;
    }
    if (!document.HasMember("source_id") || !document["source_id"].IsString() ||
        !document.HasMember("timestamp") || !document["timestamp"].IsString() ||
        !document.HasMember("objects") || !document["objects"].IsArray()) {
        LOG_WARN("External message missing required fields or has invalid types -  {}",
                 payload.c_str());
        return std::nullopt;
    }

    ExternalSourceMessage message;
    message.source_id = document["source_id"].GetString();
    message.timestamp = document["timestamp"].GetString();
    if (document.HasMember("pose")) {
        const auto& value = document["pose"];
        if (!value.IsObject() || !value.HasMember("reference_frame") ||
            !value["reference_frame"].IsString()) {
            LOG_WARN("External message has invalid pose -  {}", payload.c_str());
            return std::nullopt;
        }
        ExternalPose pose;
        pose.reference_frame = value["reference_frame"].GetString();
        const char* position_field =
            pose.reference_frame == "wgs84" ? "lat_long_alt" : "translation";
        if (!value.HasMember(position_field) || !isNumberArray<3>(value[position_field])) {
            LOG_WARN("External message missing required position field or has invalid type -  {}",
                     payload.c_str());
            return std::nullopt;
        }
        pose.position = parseNumberArray<3>(value[position_field]);
        if (value.HasMember("rotation")) {
            if (!isNumberArray<4>(value["rotation"])) {
                LOG_WARN("External message has invalid rotation field -  {}", payload.c_str());
                return std::nullopt;
            }
            pose.rotation = parseNumberArray<4>(value["rotation"]);
        }
        if (value.HasMember("provider") && value["provider"].IsString()) {
            pose.provider = value["provider"].GetString();
        }
        message.pose = std::move(pose);
    }

    for (const auto& value : document["objects"].GetArray()) {
        if (!value.IsObject() || !value.HasMember("id") || !value["id"].IsString() ||
            !value.HasMember("category") || !value["category"].IsString() ||
            !value.HasMember("translation") || !isNumberArray<3>(value["translation"])) {
            LOG_WARN("External message missing required object fields or has invalid types -  {}",
                     payload.c_str());
            return std::nullopt;
        }
        ExternalDetection detection;
        detection.id = value["id"].GetString();
        detection.category = value["category"].GetString();
        detection.translation = parseNumberArray<3>(value["translation"]);
        if (value.HasMember("rotation")) {
            if (!isNumberArray<4>(value["rotation"])) {
                LOG_WARN("External message has invalid rotation field for object -  {}",
                         payload.c_str());
                return std::nullopt;
            }
            detection.rotation = parseNumberArray<4>(value["rotation"]);
        }
        if (value.HasMember("size")) {
            if (!isNumberArray<3>(value["size"])) {
                LOG_WARN("External message has invalid size field for object -  {}",
                         payload.c_str());
                return std::nullopt;
            }
            detection.size = parseNumberArray<3>(value["size"]);
        }
        if (value.HasMember("confidence") && value["confidence"].IsNumber()) {
            detection.confidence = value["confidence"].GetDouble();
        }
        if (value.HasMember("metadata") && value["metadata"].IsObject()) {
            rapidjson::StringBuffer buffer;
            rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
            value["metadata"].Accept(writer);
            detection.metadata_json = buffer.GetString();
        }
        message.objects.push_back(std::move(detection));
    }
    return message;
}

std::vector<const Scene*>
MessageHandler::resolveExternalScenes(const std::string& publisher_id,
                                      const ExternalSourceMessage& message,
                                      std::chrono::system_clock::time_point when) {
    std::vector<const Scene*> scenes;
    const auto binding = external_scene_bindings_.find(publisher_id);
    if (binding != external_scene_bindings_.end()) {
        return binding->second;
    }
    if (!message.pose.has_value()) {
        for (const auto& scene_id : external_pose_cache_.scenesWithLiveCache(publisher_id, when)) {
            if (const auto* scene = scene_registry_.find_scene_by_id(scene_id)) {
                LOG_INFO("Resolved external scenes pose - pushing scene_id '{}'", scene_id);
                scenes.push_back(scene);
            }
        }
    } else if (message.pose->reference_frame == "wgs84") {
        for (const auto& scene : scene_registry_.get_all_scenes()) {
            if (scene.trs_matrix.has_value()) {
                scenes.push_back(&scene);
            }
        }
    }
    return scenes;
}

void MessageHandler::handleExternalSourceMessage(const std::string& topic,
                                                 const std::string& payload) {
    ObservabilityContext obs_ctx;
    obs_ctx.captureReceiveTime();
    received_count_++;
    const auto topic_parts = extractExternalTopic(topic);
    const auto message = parseExternalSourceMessage(payload);
    if (!topic_parts.has_value() || !message.has_value() ||
        message->source_id != topic_parts->first) {
        rejected_count_++;
        obs_ctx.abort(kReasonRejectedSchema);
        return;
    }
    const auto timestamp = parseTimestamp(message->timestamp);
    if (!timestamp.has_value()) {
        rejected_count_++;
        obs_ctx.abort(kReasonRejectedParse);
        return;
    }
    if (isMessageLagged(*timestamp)) {
        lagged_count_++;
        obs_ctx.abort(kReasonRejectedLag);
        return;
    }
    const auto scenes = resolveExternalScenes(topic_parts->first, *message, *timestamp);

    for (const auto* scene : scenes) {
        const bool trusted =
            external_sources_config_.trusted_positioning_sources.contains(message->source_id);
        const auto pose = external_pose_cache_.resolve(*scene, message->source_id, message->pose,
                                                       *timestamp, trusted);
        if (!pose.source_to_scene.has_value()) {
            LOG_WARN("External source pose unavailable for source={} scene={}: {}",
                     message->source_id, scene->uid, pose.reason);
            continue;
        }

        DetectionBatch batch;
        batch.source = DetectionBatch::Source::External;
        batch.receive_time = std::chrono::steady_clock::now();
        batch.timestamp = *timestamp;
        batch.timestamp_iso = message->timestamp;
        batch.obs_ctx = obs_ctx;
        batch.obs_ctx.scene_id = scene->uid;
        batch.obs_ctx.category = topic_parts->second;
        for (const auto& object : message->objects) {
            if (object.category != topic_parts->second) {
                LOG_WARN("Rejecting external object id={} source={}: category '{}' does not match "
                         "topic category '{}'",
                         object.id, message->source_id, object.category, topic_parts->second);
                continue;
            }
            const auto claim = identity_claim_registry_.claim(
                scene->uid, topic_parts->second, message->source_id, object.id, *timestamp);
            if (!claim.first) {
                LOG_WARN("Rejecting colliding external object id={} source={} scene={}", object.id,
                         message->source_id, scene->uid);
                continue;
            }
            auto transformed = object;
            transformed.translation =
                transformExternalPoint(*pose.source_to_scene, object.translation);
            batch.external_detections.push_back(std::move(transformed));
        }
        if (batch.external_detections.empty()) {
            continue;
        }

        const TrackingScope scope{scene->uid, topic_parts->second};
        {
            std::lock_guard lock(categories_mutex_);
            active_scopes_.insert(scope);
        }
        batch.obs_ctx.captureBufferTime();
        buffer_.add(scope, message->source_id, std::move(batch));
        buffered_count_++;
        Metrics::inc_messages({{kAttrScene, scene->uid},
                               {kAttrCameraId, message->source_id},
                               {kAttrReason, kReasonAccepted}});
    }
}

void MessageHandler::handleDatabaseUpdateMessage(const std::string& topic,
                                                 [[maybe_unused]] const std::string& payload) {
    LOG_INFO_ENTRY(LogEntry("Database update received, triggering restart")
                       .component("message_handler")
                       .mqtt({.topic = topic, .direction = "subscribe"}));

    if (shutdown_callback_) {
        shutdown_callback_();
    } else {
        LOG_WARN("Database update received but no shutdown callback registered");
    }
}

void MessageHandler::handleCameraMessage(const std::string& topic, const std::string& payload) {
    ObservabilityContext obs_ctx;
    obs_ctx.captureReceiveTime();
    received_count_++;

    std::string_view camera_id_view = extractCameraId(topic);
    if (camera_id_view.empty()) {
        LOG_WARN("Failed to extract camera_id from topic: {}", topic);
        rejected_count_++;
        obs_ctx.abort(kReasonRejectedParse);
        return;
    }
    std::string camera_id{camera_id_view}; // Single allocation for valid IDs only
    obs_ctx.camera_id = camera_id;

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
        obs_ctx.abort(kReasonRejectedSchema);
        return;
    }

    obs_ctx.captureParseTime();

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
                .error({.type = "unknown_camera", .message = "Camera not in scene registry"}));
        rejected_count_++;
        obs_ctx.abort(kReasonRejectedUnknownTopic);
        return;
    }

    // Parse timestamp once (reused for lag check and batch storage)
    auto msg_time = parseTimestamp(message->timestamp);
    if (!msg_time) {
        LOG_WARN("Failed to parse timestamp '{}' from camera '{}', dropping", message->timestamp,
                 camera_id);
        rejected_count_++;
        obs_ctx.abort(kReasonRejectedParse);
        return;
    }

    // Check for lag
    if (isMessageLagged(*msg_time)) {
        LOG_WARN_ENTRY(
            LogEntry("Dropping lagged message")
                .component("message_handler")
                .domain({.camera_id = camera_id, .scene_id = scene->uid})
                .error({.type = "fell_behind", .message = "Message timestamp exceeds max_lag_s"}));
        lagged_count_++;
        obs_ctx.abort(kReasonRejectedLag);
        return;
    }

    obs_ctx.scene_id = scene->uid;

    // Push detections to buffer for each active scope in this scene.
    // Active scopes are accumulated as new (scene, category) pairs are seen in messages.
    // Empty batches (no detections) are created for scopes not present in the current message,
    // allowing the Kalman filter to advance time-steps and age out stale tracks.
    auto receive_time = std::chrono::steady_clock::now();

    // Under lock: validate new categories, update active_scopes_, collect scene's active scopes.
    std::vector<TrackingScope> scene_scopes;
    {
        std::lock_guard<std::mutex> lock(categories_mutex_);
        for (const auto& [category, _] : message->objects) {
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
            active_scopes_.insert(TrackingScope{scene->uid, category});
        }
        for (const auto& scope : active_scopes_) {
            if (scope.scene_id == scene->uid) {
                scene_scopes.push_back(scope);
            }
        }
    } // Lock released before buffer operations

    for (const auto& scope : scene_scopes) {
        const auto& category = scope.category;

        DetectionBatch batch;
        batch.camera_id = camera_id;
        batch.receive_time = receive_time;
        batch.timestamp_iso = message->timestamp;
        batch.timestamp = *msg_time;
        batch.obs_ctx = obs_ctx; // Copy obs_ctx to allow reuse in next loop iteration
        batch.obs_ctx.captureBufferTime();
        batch.obs_ctx.category = category;

        // Use detections from the message if present; empty batch otherwise (enables track aging).
        auto det_it = message->objects.find(category);
        if (det_it != message->objects.end()) {
            batch.detections = std::move(det_it->second);
        }

        buffer_.add(scope, camera_id, std::move(batch));
        buffered_count_++;

        LOG_DEBUG_ENTRY(
            LogEntry("Buffered detections")
                .component("message_handler")
                .domain(
                    {.camera_id = camera_id, .scene_id = scene->uid, .object_category = category}));
    }

    // Record message accepted
    Metrics::inc_messages({{kAttrScene, std::string(scene->uid)},
                           {kAttrCameraId, camera_id},
                           {kAttrReason, kReasonAccepted}});
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

            detection.bounding_box_px = cv::Rect2f(static_cast<float>(bbox_x->GetDouble()),
                                                   static_cast<float>(bbox_y->GetDouble()),
                                                   static_cast<float>(bbox_width->GetDouble()),
                                                   static_cast<float>(bbox_height->GetDouble()));

            // Optional metadata - serialize the entire metadata object as a raw JSON string
            if (det.HasMember("metadata") && det["metadata"].IsObject()) {
                rapidjson::StringBuffer meta_buf;
                rapidjson::Writer<rapidjson::StringBuffer> meta_writer(meta_buf);
                det["metadata"].Accept(meta_writer);
                detection.metadata_json = meta_buf.GetString();
            }

            // Optional confidence score
            if (det.HasMember("confidence") && det["confidence"].IsNumber()) {
                detection.confidence = det["confidence"].GetDouble();
            }

            detections.push_back(detection);
        }

        message.objects[category] = std::move(detections);
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

bool MessageHandler::isMessageLagged(std::chrono::system_clock::time_point msg_time) const {
    auto now = clock_fn_();
    auto lag = std::chrono::duration<double>(now - msg_time).count();
    if (lag > tracking_config_.max_lag_s) {
        LOG_DEBUG("Message lag check: lag={:.3f}s, max_lag={:.3f}s", lag,
                  tracking_config_.max_lag_s);
        return true;
    }
    return false;
}

} // namespace tracker
