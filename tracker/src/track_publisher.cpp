// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "track_publisher.hpp"

#include "logger.hpp"

#include <format>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker {

TrackPublisher::TrackPublisher(std::shared_ptr<IMqttClient> mqtt_client)
    : mqtt_client_(std::move(mqtt_client)) {}

void TrackPublisher::publish(const std::string& scene_id, const std::string& scene_name,
                             const std::string& category, const std::string& timestamp,
                             const std::vector<Track>& tracks) {
    if (!mqtt_client_ || !mqtt_client_->isConnected()) {
        LOG_WARN("Cannot publish tracks: MQTT client not connected");
        return;
    }

    std::string topic = build_topic(scene_id, category);
    std::string payload = serialize(scene_id, scene_name, timestamp, tracks);

    mqtt_client_->publish(topic, payload);
    published_count_.fetch_add(1);

    LOG_DEBUG("Published {} tracks to {} (size={})", tracks.size(), topic, payload.size());
}

std::string TrackPublisher::serialize(const std::string& scene_id, const std::string& scene_name,
                                      const std::string& timestamp,
                                      const std::vector<Track>& tracks) {
    using namespace rapidjson;

    Document doc;
    doc.SetObject();
    auto& allocator = doc.GetAllocator();

    // Scene metadata
    doc.AddMember("id", Value().SetString(scene_id.c_str(), allocator), allocator);
    doc.AddMember("name", Value().SetString(scene_name.c_str(), allocator), allocator);
    doc.AddMember("timestamp", Value().SetString(timestamp.c_str(), allocator), allocator);

    // Objects array
    Value objects_array(kArrayType);
    objects_array.Reserve(static_cast<SizeType>(tracks.size()), allocator);

    for (const auto& track : tracks) {
        Value obj(kObjectType);

        obj.AddMember(
            "id",
            Value().SetString(track.id.c_str(), static_cast<SizeType>(track.id.size()), allocator),
            allocator);
        obj.AddMember("category", Value().SetString(track.category.c_str(), allocator), allocator);

        // Translation [x, y, z]
        Value translation(kArrayType);
        translation.Reserve(3, allocator);
        translation.PushBack(track.translation[0], allocator);
        translation.PushBack(track.translation[1], allocator);
        translation.PushBack(track.translation[2], allocator);
        obj.AddMember("translation", translation, allocator);

        // Velocity [vx, vy, vz]
        Value velocity(kArrayType);
        velocity.Reserve(3, allocator);
        velocity.PushBack(track.velocity[0], allocator);
        velocity.PushBack(track.velocity[1], allocator);
        velocity.PushBack(track.velocity[2], allocator);
        obj.AddMember("velocity", velocity, allocator);

        // Size [length, width, height]
        Value size(kArrayType);
        size.Reserve(3, allocator);
        size.PushBack(track.size[0], allocator);
        size.PushBack(track.size[1], allocator);
        size.PushBack(track.size[2], allocator);
        obj.AddMember("size", size, allocator);

        // Rotation quaternion [x, y, z, w]
        Value rotation(kArrayType);
        rotation.Reserve(4, allocator);
        rotation.PushBack(track.rotation[0], allocator);
        rotation.PushBack(track.rotation[1], allocator);
        rotation.PushBack(track.rotation[2], allocator);
        rotation.PushBack(track.rotation[3], allocator);
        obj.AddMember("rotation", rotation, allocator);

        objects_array.PushBack(obj, allocator);
    }

    doc.AddMember("objects", objects_array, allocator);

    // Serialize to string
    StringBuffer buffer;
    Writer<StringBuffer> writer(buffer);
    doc.Accept(writer);

    return std::string(buffer.GetString(), buffer.GetSize());
}

std::string TrackPublisher::build_topic(const std::string& scene_id, const std::string& category) {
    return std::format("scenescape/data/scene/{}/{}", scene_id, category);
}

} // namespace tracker
