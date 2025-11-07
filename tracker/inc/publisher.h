#pragma once

#include "mqtt_msg.h"
#include "rv/tracking/TrackedObject.hpp"
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <vector>

class MqttClient;

class Publisher {
public:
    Publisher(MqttClient& client);
    ~Publisher();

    // Disable copy
    Publisher(const Publisher&) = delete;
    Publisher& operator=(const Publisher&) = delete;

    // Publish a message synchronously
    void publish(const std::string& topic, const std::string& scene_id,
                 const std::string& scene_name, const std::string& camera_id,
                 const std::vector<rv::tracking::TrackedObject>& tracks,
                 std::chrono::system_clock::time_point timestamp);

    // Stop the publisher thread
    void stop();

private:
    void run();

    MqttClient& client_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    bool should_exit_;
    std::thread publisher_thread_;
};
