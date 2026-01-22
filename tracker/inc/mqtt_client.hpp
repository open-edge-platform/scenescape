// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include <mqtt/async_client.h>

namespace tracker {

/**
 * @brief MQTT client wrapper with automatic reconnection and TLS support.
 *
 * Provides a simplified interface for MQTT pub/sub with:
 * - Automatic reconnection with exponential backoff (1s → 30s max)
 * - TLS/mTLS connection support
 * - Thread-safe connection state queries
 * - QoS 1 for all publish/subscribe operations
 */
class MqttClient : public mqtt::callback, public mqtt::iaction_listener {
  public:
    // MQTT QoS: 0=at-most-once (can drop), 1=at-least-once (may duplicate), 2=exactly-once (highest overhead)
    static constexpr int MQTT_QOS = 1;

    /// Callback type for received messages: (topic, payload) -> void
    using MessageCallback = std::function<void(const std::string&, const std::string&)>;

    /**
     * @brief Construct MQTT client from configuration.
     *
     * @param config MQTT configuration with host, port, SSL settings
     * @param max_reconnect_delay_s Maximum reconnection delay in seconds (default: 30)
     */
    explicit MqttClient(const MqttConfig& config, int max_reconnect_delay_s = 30);

    ~MqttClient();

    // Non-copyable, non-movable (owns async resources)
    MqttClient(const MqttClient&) = delete;
    MqttClient& operator=(const MqttClient&) = delete;
    MqttClient(MqttClient&&) = delete;
    MqttClient& operator=(MqttClient&&) = delete;

    /**
     * @brief Start connection to MQTT broker.
     *
     * Initiates async connection. Use isConnected() to check state.
     * Reconnection is handled automatically on disconnect.
     */
    void connect();

    /**
     * @brief Disconnect from MQTT broker with graceful drain.
     *
     * @param drain_timeout Timeout for pending publishes (default: 2s per design)
     */
    void disconnect(std::chrono::milliseconds drain_timeout = std::chrono::milliseconds(2000));

    /**
    * @brief Subscribe to a topic with QoS 1.
     *
     * @param topic Topic pattern (wildcards supported)
     */
    void subscribe(const std::string& topic);

    /**
    * @brief Publish a message with QoS 1.
     *
     * @param topic Topic to publish to
     * @param payload Message payload (JSON string)
     */
    void publish(const std::string& topic, const std::string& payload);

    /**
     * @brief Set callback for received messages.
     *
     * @param callback Function called with (topic, payload) on message arrival
     */
    void setMessageCallback(MessageCallback callback);

    /**
     * @brief Check if connected to broker.
     *
     * Thread-safe.
     */
    [[nodiscard]] bool isConnected() const;

    /**
     * @brief Check if subscribed to topics.
     *
     * Thread-safe.
     */
    [[nodiscard]] bool isSubscribed() const;

    /**
     * @brief Generate client ID in format tracker-{hostname}-{pid}.
     */
    static std::string generateClientId();

  private:
    // mqtt::callback interface
    void connected(const std::string& cause) override;
    void connection_lost(const std::string& cause) override;
    void message_arrived(mqtt::const_message_ptr msg) override;

    // mqtt::iaction_listener interface
    void on_success(const mqtt::token& tok) override;
    void on_failure(const mqtt::token& tok) override;

    /**
     * @brief Build SSL options from config.
     */
    mqtt::ssl_options buildSslOptions() const;

    /**
     * @brief Schedule reconnection with exponential backoff.
     */
    void scheduleReconnect();

    /**
     * @brief Reconnection worker thread function.
     */
    void reconnectWorker();

    /**
     * @brief Calculate next backoff delay.
     *
     * @return Delay in milliseconds
     */
    std::chrono::milliseconds calculateBackoff();

    // Configuration
    MqttConfig config_;
    int max_reconnect_delay_s_;
    std::string client_id_;
    std::string pending_subscription_;

    // Paho client
    std::unique_ptr<mqtt::async_client> client_;
    mqtt::connect_options conn_opts_;

    // State
    std::atomic<bool> connected_{false};
    std::atomic<bool> subscribed_{false};
    std::atomic<bool> stop_requested_{false};

    // Reconnection
    std::thread reconnect_thread_;
    std::mutex reconnect_mutex_;
    std::condition_variable reconnect_cv_;
    int reconnect_attempt_{0};

    // Callbacks
    MessageCallback message_callback_;
    std::mutex callback_mutex_;
};

} // namespace tracker
