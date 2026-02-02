// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>

#include <mqtt/async_client.h>

namespace tracker {

/**
 * @brief Abstract interface for MQTT client operations.
 *
 * Enables dependency injection and mocking for unit tests.
 * Implementations should provide connection management, pub/sub, and callbacks.
 */
class IMqttClient {
public:
    /// Callback type for received messages: (topic, payload) -> void
    using MessageCallback = std::function<void(const std::string&, const std::string&)>;

    virtual ~IMqttClient() = default;

    /**
     * @brief Start connection to MQTT broker.
     */
    virtual void connect() = 0;

    /**
     * @brief Disconnect from MQTT broker.
     *
     * @param drain_timeout Timeout for pending publishes
     */
    virtual void
    disconnect(std::chrono::milliseconds drain_timeout = std::chrono::milliseconds(2000)) = 0;

    /**
     * @brief Subscribe to a topic.
     *
     * @param topic Topic pattern (wildcards supported)
     */
    virtual void subscribe(const std::string& topic) = 0;

    /**
     * @brief Unsubscribe from a topic.
     *
     * @param topic Topic pattern to unsubscribe from
     */
    virtual void unsubscribe(const std::string& topic) = 0;

    /**
     * @brief Publish a message.
     *
     * @param topic Topic to publish to
     * @param payload Message payload
     */
    virtual void publish(const std::string& topic, const std::string& payload) = 0;

    /**
     * @brief Set callback for received messages.
     *
     * @param callback Function called with (topic, payload) on message arrival
     */
    virtual void setMessageCallback(MessageCallback callback) = 0;

    /**
     * @brief Check if connected to broker.
     */
    [[nodiscard]] virtual bool isConnected() const = 0;

    /**
     * @brief Check if subscribed to topics.
     */
    [[nodiscard]] virtual bool isSubscribed() const = 0;
};

/**
 * @brief MQTT client wrapper with automatic reconnection and TLS support.
 *
 * Provides a simplified interface for MQTT pub/sub with:
 * - Automatic reconnection with exponential backoff (1s → 30s max)
 * - TLS/mTLS connection support
 * - Thread-safe connection state queries
 * - QoS 1 for all publish/subscribe operations
 */
class MqttClient : public IMqttClient, public mqtt::callback, public mqtt::iaction_listener {
public:
    // MQTT QoS: 0=at-most-once (can drop), 1=at-least-once (may duplicate), 2=exactly-once (highest
    // overhead)
    static constexpr int MQTT_QOS = 1;

    /// Callback type for received messages: (topic, payload) -> void
    using MessageCallback = IMqttClient::MessageCallback;

    /**
     * @brief Construct MQTT client from configuration.
     *
     * @param config MQTT configuration with host, port, SSL settings
     * @param max_reconnect_delay_s Maximum reconnection delay in seconds (default: 30)
     */
    explicit MqttClient(const MqttConfig& config, int max_reconnect_delay_s = 30);

    ~MqttClient() override;

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
    void connect() override;

    /**
     * @brief Disconnect from MQTT broker with graceful drain.
     *
     * @param drain_timeout Timeout for pending publishes (default: 2s per design)
     */
    void
    disconnect(std::chrono::milliseconds drain_timeout = std::chrono::milliseconds(2000)) override;

    /**
     * @brief Subscribe to a topic with QoS 1.
     *
     * @param topic Topic pattern (wildcards supported)
     */
    void subscribe(const std::string& topic) override;

    /**
     * @brief Unsubscribe from a topic.
     *
     * @param topic Topic pattern to unsubscribe from
     */
    void unsubscribe(const std::string& topic) override;

    /**
     * @brief Publish a message with QoS 1.
     *
     * @param topic Topic to publish to
     * @param payload Message payload (JSON string)
     */
    void publish(const std::string& topic, const std::string& payload) override;

    /**
     * @brief Set callback for received messages.
     *
     * @param callback Function called with (topic, payload) on message arrival
     */
    void setMessageCallback(MessageCallback callback) override;

    /**
     * @brief Check if connected to broker.
     *
     * Thread-safe.
     */
    [[nodiscard]] bool isConnected() const override;

    /**
     * @brief Check if subscribed to topics.
     *
     * Thread-safe.
     */
    [[nodiscard]] bool isSubscribed() const override;

    /**
     * @brief Generate client ID in format tracker-{hostname}-{pid}.
     */
    static std::string generateClientId();

    /**
     * @brief Calculate exponential backoff delay for reconnection.
     *
     * Pure function exposed for unit testing. Uses exponential backoff:
     * 1s, 2s, 4s, 8s, 16s, then capped at max_delay_s.
     *
     * @param attempt Current reconnection attempt number (0-based)
     * @param initial_ms Initial backoff delay in milliseconds (default: 1000)
     * @param max_delay_s Maximum delay in seconds (default: 30)
     * @return Delay in milliseconds
     */
    static std::chrono::milliseconds calculateBackoff(int attempt, int initial_ms = 1000,
                                                      int max_delay_s = 30);

private:
    // mqtt::callback interface
    void connected(const std::string& cause) override;
    void connection_lost(const std::string& cause) override;
    void message_arrived(mqtt::const_message_ptr msg) override;

    // mqtt::iaction_listener interface
    void on_success(const mqtt::token& tok) override;
    void on_failure(const mqtt::token& tok) override;

    /**
     * @brief Build TLS options from config.
     */
    mqtt::ssl_options buildTlsOptions() const;

    /**
     * @brief Schedule reconnection with exponential backoff.
     */
    void scheduleReconnect();

    /**
     * @brief Reconnection worker thread function.
     */
    void reconnectWorker();

    // Configuration
    MqttConfig config_;
    int max_reconnect_delay_s_;
    std::string client_id_;
    std::set<std::string> pending_subscriptions_;
    mutable std::mutex subscriptions_mutex_;

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
    std::atomic<bool> reconnecting_{false};
    int reconnect_attempt_{0};

    // Callbacks
    MessageCallback message_callback_;
    std::mutex callback_mutex_;
};

} // namespace tracker
