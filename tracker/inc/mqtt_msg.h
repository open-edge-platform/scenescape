#pragma once

#include "entities.h"
#include "rv/tracking/TrackedObject.hpp"
#include <chrono>
#include <ostream>
#include <string>
#include <vector>

namespace simdjson::dom {
class element;
}

// Helper to parse ISO 8601 timestamp string to time_point
std::chrono::system_clock::time_point parse_timestamp(const std::string& timestamp);

struct CameraDetectionMsg {
    std::string id;
    std::string debug_mac;
    std::string timestamp;
    std::string debug_timestamp_end;
    double debug_processing_time;
    double rate;
    std::vector<Person> persons;

    // Convert timestamp string to time_point
    std::chrono::system_clock::time_point get_timestamp() const;

    // Parse from JSON using simdjson
    static CameraDetectionMsg parse(const simdjson::dom::element& doc);
};

struct UnregulatedTrackMsg {
    std::string scene_id;
    std::string scene_name;
    std::string camera_id;
    std::string timestamp;
    std::vector<rv::tracking::TrackedObject> objects;

    // Convert timestamp string to time_point
    std::chrono::system_clock::time_point get_timestamp() const;

    // Create message from tracked objects
    static UnregulatedTrackMsg create(const std::string& scene_id, const std::string& scene_name,
                                      const std::string& camera_id,
                                      const std::vector<rv::tracking::TrackedObject>& objects,
                                      std::chrono::system_clock::time_point timestamp);

    // Serialize to JSON string using RapidJSON
    std::string toJson() const;
};

// Stream output operators
std::ostream& operator<<(std::ostream& os, const CameraDetectionMsg& msg);
std::ostream& operator<<(std::ostream& os, const UnregulatedTrackMsg& msg);
