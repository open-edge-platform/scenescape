#include "mqtt_msg.h"
#include "simdjson.h"
#include "time_utils.h"
#include <chrono>
#include <format>
#include <iomanip>
#include <iostream>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <sstream>

// parse_timestamp now lives in time_utils.cpp and is declared in time_utils.h

template <typename T>
T parse_field(const simdjson::dom::element& elem, const std::string& field_name) {
    try {
        if constexpr (std::is_same_v<T, std::string>) {
            return std::string(elem);
        } else if constexpr (std::is_same_v<T, double>) {
            // Handle both number and string types for doubles
            if (elem.type() == simdjson::dom::element_type::STRING) {
                return std::stod(std::string(elem));
            }
            return double(elem);
        } else if constexpr (std::is_same_v<T, int64_t>) {
            // Handle float to int conversion
            return static_cast<int64_t>(double(elem));
        }
    } catch (const std::exception& e) {
        std::cerr << "ERROR parsing field '" << field_name << "': " << e.what() << std::endl;
        throw;
    }
}

std::ostream& operator<<(std::ostream& os, const CameraDetectionMsg& msg) {
    os << "CameraDetectionMsg {\n"
       << "  id: " << msg.id << "\n"
       << "  timestamp: " << msg.timestamp << "\n"
       << "  processing_time: " << std::fixed << std::setprecision(4) << msg.debug_processing_time
       << " ms\n"
       << "  rate: " << msg.rate << "\n"
       << "  persons: " << msg.persons.size() << " detected\n";

    for (size_t i = 0; i < msg.persons.size(); ++i) {
        os << "  [" << i << "] " << msg.persons[i];
        if (i < msg.persons.size() - 1) {
            os << "\n";
        }
    }

    os << "\n}";
    return os;
}

std::chrono::system_clock::time_point CameraDetectionMsg::get_timestamp() const {
    return parse_timestamp(timestamp);
}

CameraDetectionMsg CameraDetectionMsg::parse(const simdjson::dom::element& doc) {
    CameraDetectionMsg msg;

    msg.id = parse_field<std::string>(doc["id"], "id");
    msg.debug_mac = parse_field<std::string>(doc["debug_mac"], "debug_mac");
    msg.timestamp = parse_field<std::string>(doc["timestamp"], "timestamp");
    msg.debug_timestamp_end =
        parse_field<std::string>(doc["debug_timestamp_end"], "debug_timestamp_end");
    msg.debug_processing_time =
        parse_field<double>(doc["debug_processing_time"], "debug_processing_time");
    msg.rate = parse_field<double>(doc["rate"], "rate");

    // Parse persons array if it exists (empty is valid - means no detections)
    auto objects = doc["objects"];
    if (objects.at_key("person").error() == simdjson::SUCCESS) {
        try {
            for (auto person_elem : objects["person"].get_array()) {
                Person p;
                p.category = parse_field<std::string>(person_elem["category"], "category");
                p.confidence = parse_field<double>(person_elem["confidence"], "confidence");
                p.center_of_mass.x =
                    parse_field<double>(person_elem["center_of_mass"]["x"], "center_of_mass.x");
                p.center_of_mass.y =
                    parse_field<double>(person_elem["center_of_mass"]["y"], "center_of_mass.y");
                p.center_of_mass.width = parse_field<double>(person_elem["center_of_mass"]["width"],
                                                             "center_of_mass.width");
                p.center_of_mass.height = parse_field<double>(
                    person_elem["center_of_mass"]["height"], "center_of_mass.height");
                p.bounding_box_px.x =
                    parse_field<int64_t>(person_elem["bounding_box_px"]["x"], "bounding_box_px.x");
                p.bounding_box_px.y =
                    parse_field<int64_t>(person_elem["bounding_box_px"]["y"], "bounding_box_px.y");
                p.bounding_box_px.width = parse_field<int64_t>(
                    person_elem["bounding_box_px"]["width"], "bounding_box_px.width");
                p.bounding_box_px.height = parse_field<int64_t>(
                    person_elem["bounding_box_px"]["height"], "bounding_box_px.height");
                p.id = parse_field<int64_t>(person_elem["id"], "id");
                msg.persons.push_back(p);
            }
        } catch (const std::exception& e) {
            std::cerr << "ERROR parsing persons array: " << e.what() << std::endl;
            throw;
        }
    }

    return msg;
}

std::ostream& operator<<(std::ostream& os, const UnregulatedTrackMsg& msg) {
    os << "UnregulatedTrackMsg {\n"
       << "  timestamp: " << msg.timestamp << "\n"
       << "  objects: " << msg.objects.size() << " tracked\n";

    for (size_t i = 0; i < msg.objects.size(); ++i) {
        const auto& obj = msg.objects[i];
        os << "  [" << i << "] TrackedObject{id=" << obj.id << ", pos=(" << obj.x << "," << obj.y
           << "," << obj.z << ")" << ", vel=(" << obj.vx << "," << obj.vy << ")" << ", size=("
           << obj.length << "x" << obj.width << "x" << obj.height << ")";
        if (i < msg.objects.size() - 1) {
            os << "\n";
        }
    }

    os << "\n}";
    return os;
}

std::chrono::system_clock::time_point UnregulatedTrackMsg::get_timestamp() const {
    return parse_timestamp(timestamp);
}

UnregulatedTrackMsg
UnregulatedTrackMsg::create(const std::string& scene_id, const std::string& scene_name,
                            const std::string& camera_id,
                            const std::vector<rv::tracking::TrackedObject>& objects,
                            std::chrono::system_clock::time_point timestamp) {
    UnregulatedTrackMsg msg;
    msg.scene_id = scene_id;
    msg.scene_name = scene_name;
    msg.camera_id = camera_id;
    msg.objects = objects;

    // Convert time_point to strict RFC3339 with milliseconds and 'Z'
    auto tp_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(timestamp);
    msg.timestamp = std::format("{:%FT%T}", tp_ms) + "Z";
    return msg;
}

std::string UnregulatedTrackMsg::toJson() const {
    rapidjson::Document doc;
    doc.SetObject();
    auto& allocator = doc.GetAllocator();

    // Add scene ID as "id" field
    doc.AddMember("id", rapidjson::Value(scene_id.c_str(), allocator), allocator);

    // Add timestamp
    doc.AddMember("timestamp", rapidjson::Value(timestamp.c_str(), allocator), allocator);

    // Add scene name
    doc.AddMember("name", rapidjson::Value(scene_name.c_str(), allocator), allocator);

    // Add objects array in required format
    rapidjson::Value objects_array(rapidjson::kArrayType);
    for (const auto& obj : objects) {
        rapidjson::Value track_obj(rapidjson::kObjectType);

        track_obj.AddMember("id", obj.id, allocator);
        track_obj.AddMember("category", "person", allocator);
        track_obj.AddMember("type", "person", allocator);

        // Translation array [x, y, z]
        rapidjson::Value translation(rapidjson::kArrayType);
        translation.PushBack(obj.x, allocator);
        translation.PushBack(obj.y, allocator);
        translation.PushBack(obj.z, allocator);
        track_obj.AddMember("translation", translation, allocator);

        // Size array [length, width, height]
        rapidjson::Value size(rapidjson::kArrayType);
        size.PushBack(obj.length, allocator);
        size.PushBack(obj.width, allocator);
        size.PushBack(obj.height, allocator);
        track_obj.AddMember("size", size, allocator);

        // Velocity array [vx, vy, 0.0]
        rapidjson::Value velocity(rapidjson::kArrayType);
        velocity.PushBack(obj.vx, allocator);
        velocity.PushBack(obj.vy, allocator);
        velocity.PushBack(0.0, allocator);
        track_obj.AddMember("velocity", velocity, allocator);

        // Rotation quaternion [0, 0, 0, 1] - identity for now
        rapidjson::Value rotation(rapidjson::kArrayType);
        rotation.PushBack(0, allocator);
        rotation.PushBack(0, allocator);
        rotation.PushBack(0, allocator);
        rotation.PushBack(1, allocator);
        track_obj.AddMember("rotation", rotation, allocator);

        // Visibility array with camera ID
        rapidjson::Value visibility(rapidjson::kArrayType);
        visibility.PushBack(rapidjson::Value(camera_id.c_str(), allocator), allocator);
        track_obj.AddMember("visibility", visibility, allocator);

        // Additional fields to match format
        track_obj.AddMember("similarity", rapidjson::Value().SetNull(), allocator);
        track_obj.AddMember("first_seen", rapidjson::Value(timestamp.c_str(), allocator),
                            allocator);

        objects_array.PushBack(track_obj, allocator);
    }
    doc.AddMember("objects", objects_array, allocator);

    // Serialize to string
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    doc.Accept(writer);

    return std::string(buffer.GetString(), buffer.GetSize());
}
