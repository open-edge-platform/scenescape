#pragma once

#include "config.h"
#include "mqtt_msg.h"
#include "rv/tracking/TrackedObject.hpp"
#include <chrono>
#include <functional>
#include <memory>
#include <string>
#include <vector>

// Callback type for message handling
using MessageCallback = std::function<void(const CameraDetectionMsg&)>;
using ConnectionStateCallback = std::function<void(bool)>; // true=connected, false=disconnected

class MqttClient {
public:
    MqttClient(const std::string& server_address, const std::string& client_id);
    MqttClient(const std::string& server_address, const std::string& client_id,
               const SslConfig& ssl_config);
    ~MqttClient();

    // Disable copy
    MqttClient(const MqttClient&) = delete;
    MqttClient& operator=(const MqttClient&) = delete;

    void connect();
    void disconnect();
    void subscribe(const std::string& topic, int qos = 1);
    void subscribe(const std::vector<std::string>& topics, int qos = 1);
    void unsubscribe(const std::string& topic);
    void unsubscribe(const std::vector<std::string>& topics);
    void publish(const std::string& topic, const UnregulatedTrackMsg& msg, int qos = 1);
    void set_message_callback(MessageCallback callback);
    void set_connection_state_callback(ConnectionStateCallback callback);

    bool is_connected() const;

private:
    class Impl;
    std::unique_ptr<Impl> pImpl_;
};
