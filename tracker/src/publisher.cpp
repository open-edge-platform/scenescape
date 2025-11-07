#include "publisher.h"
#include "logger.h"
#include "mqtt_client.h"
#include <iostream>
#include <quill/LogMacros.h>

Publisher::Publisher(MqttClient& client)
    : client_(client), should_exit_(false), publisher_thread_(&Publisher::run, this) {}

Publisher::~Publisher() {
    stop();
    if (publisher_thread_.joinable()) {
        publisher_thread_.join();
    }
}

void Publisher::publish(const std::string& topic, const std::string& scene_id,
                        const std::string& scene_name, const std::string& camera_id,
                        const std::vector<rv::tracking::TrackedObject>& tracks,
                        std::chrono::system_clock::time_point timestamp) {
    // Create message with scene and camera information
    auto msg = UnregulatedTrackMsg::create(scene_id, scene_name, camera_id, tracks, timestamp);
    std::string json = msg.toJson();

    LOG_DEBUG(logger::get_logger(), "Publishing {} tracks to topic: {}", tracks.size(), topic);
    LOG_TRACE_L1(logger::get_logger(), "Publishing JSON: {}", json);

    client_.publish(topic, msg);
}

void Publisher::stop() {
    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        should_exit_ = true;
    }
    queue_cv_.notify_one();
}

void Publisher::run() {
    // Background thread placeholder - currently not used
    std::unique_lock<std::mutex> lock(queue_mutex_);
    queue_cv_.wait(lock, [this]() { return should_exit_; });
}
