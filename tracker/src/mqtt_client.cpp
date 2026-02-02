// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "mqtt_client.hpp"
#include "logger.hpp"
#include "proxy_utils.hpp"

#include <algorithm>
#include <filesystem>
#include <unistd.h>

namespace tracker {

namespace {

constexpr size_t HOSTNAME_BUFFER_SIZE = 256;
constexpr int INITIAL_BACKOFF_MS = 1000;
constexpr int MAX_BACKOFF_MULTIPLIER = 30; // 30s max with 1s initial
constexpr int KEEPALIVE_SECONDS = 60;
constexpr int CONNECT_TIMEOUT_SECONDS = 10;
constexpr int DISCONNECT_WAIT_MS = 500;
constexpr int RECONNECT_POST_CONNECT_DELAY_MS = 100;

std::string getHostname() {
    char hostname[HOSTNAME_BUFFER_SIZE];
    if (gethostname(hostname, sizeof(hostname)) == 0) {
        hostname[HOSTNAME_BUFFER_SIZE - 1] = '\0';
        return std::string(hostname);
    }
    return "unknown";
}

} // namespace

std::string MqttClient::generateClientId() {
    return "tracker-" + getHostname() + "-" + std::to_string(getpid());
}

MqttClient::MqttClient(const MqttConfig& config, int max_reconnect_delay_s)
    : config_(config), max_reconnect_delay_s_(max_reconnect_delay_s),
      client_id_(generateClientId()) {
    clearEmptyProxyEnvVars();

    std::string server_uri;
    if (config_.insecure) {
        server_uri = "tcp://" + config_.host + ":" + std::to_string(config_.port);
    } else {
        server_uri = "ssl://" + config_.host + ":" + std::to_string(config_.port);
    }

    LOG_INFO("MQTT client initializing: {} (client_id: {})", server_uri, client_id_);

    client_ = std::make_unique<mqtt::async_client>(server_uri, client_id_);
    client_->set_callback(*this);

    // Build connection options
    auto conn_opts_builder = mqtt::connect_options_builder()
                                 .clean_session(true)
                                 .automatic_reconnect(false) // We handle reconnection ourselves
                                 .keep_alive_interval(std::chrono::seconds(KEEPALIVE_SECONDS))
                                 .connect_timeout(std::chrono::seconds(CONNECT_TIMEOUT_SECONDS));

    if (!config_.insecure) {
        conn_opts_builder.ssl(buildTlsOptions());
    }

    conn_opts_ = conn_opts_builder.finalize();
}

MqttClient::~MqttClient() {
    disconnect();
}

mqtt::ssl_options MqttClient::buildTlsOptions() const {
    auto ssl_opts_builder = mqtt::ssl_options_builder();

    if (config_.tls.has_value()) {
        const auto& tls = config_.tls.value();

        LOG_DEBUG("TLS config: ca_cert='{}', client_cert='{}', client_key='{}', verify={}",
                  tls.ca_cert_path, tls.client_cert_path, tls.client_key_path, tls.verify_server);

        // Validate required TLS files exist
        if (!tls.ca_cert_path.empty()) {
            if (!std::filesystem::exists(tls.ca_cert_path)) {
                LOG_ERROR("TLS CA certificate file not found: {}", tls.ca_cert_path);
                throw std::runtime_error("TLS CA certificate file not found: " + tls.ca_cert_path);
            }
            ssl_opts_builder.trust_store(tls.ca_cert_path);
        }

        if (!tls.client_cert_path.empty() && !tls.client_key_path.empty()) {
            if (!std::filesystem::exists(tls.client_cert_path)) {
                LOG_ERROR("TLS client certificate file not found: {}", tls.client_cert_path);
                throw std::runtime_error("TLS client certificate file not found: " +
                                         tls.client_cert_path);
            }
            if (!std::filesystem::exists(tls.client_key_path)) {
                LOG_ERROR("TLS client key file not found: {}", tls.client_key_path);
                throw std::runtime_error("TLS client key file not found: " + tls.client_key_path);
            }
            ssl_opts_builder.key_store(tls.client_cert_path);
            ssl_opts_builder.private_key(tls.client_key_path);
        }

        ssl_opts_builder.enable_server_cert_auth(tls.verify_server);
    } else {
        LOG_DEBUG("TLS config not set, using default SSL options");
    }

    return ssl_opts_builder.finalize();
}

void MqttClient::connect() {
    LOG_INFO("MQTT connecting to {}:{} (insecure={})", config_.host, config_.port,
             config_.insecure);

    try {
        auto tok = client_->connect(conn_opts_, nullptr, *this);
        LOG_DEBUG("MQTT connect initiated, token msg_id: {}", tok->get_message_id());
    } catch (const mqtt::exception& e) {
        LOG_ERROR("MQTT connect threw: {} (rc={})", e.what(), e.get_reason_code());
        scheduleReconnect();
    } catch (const std::exception& e) {
        LOG_ERROR("MQTT connect threw std exception: {}", e.what());
        scheduleReconnect();
    }
}

void MqttClient::disconnect(std::chrono::milliseconds drain_timeout) {
    // Guard against double-disconnect
    if (stop_requested_.exchange(true)) {
        LOG_DEBUG("MQTT disconnect already in progress or completed");
        return;
    }

    LOG_INFO("MQTT disconnecting (drain timeout: {}ms)", drain_timeout.count());

    reconnect_cv_.notify_all();

    if (reconnect_thread_.joinable()) {
        reconnect_thread_.join();
    }

    if (client_) {
        try {
            if (client_->is_connected()) {
                // Synchronous disconnect with short timeout
                auto tok = client_->disconnect();
                tok->wait_for(std::chrono::milliseconds(DISCONNECT_WAIT_MS));
                LOG_DEBUG("MQTT disconnect completed");
            }
        } catch (const mqtt::exception& e) {
            LOG_WARN("MQTT disconnect error: {}", e.what());
        } catch (const std::exception& e) {
            LOG_WARN("MQTT disconnect std error: {}", e.what());
        }
    }

    connected_ = false;
    subscribed_ = false;
}

void MqttClient::subscribe(const std::string& topic) {
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        pending_subscriptions_.insert(topic);
    }

    if (!connected_) {
        LOG_DEBUG("MQTT subscribe deferred (not connected): {}", topic);
        return;
    }

    LOG_INFO("MQTT subscribing to: {} (QoS {})", topic, MQTT_QOS);

    try {
        client_->subscribe(topic, MQTT_QOS, nullptr, *this);
    } catch (const mqtt::exception& e) {
        LOG_ERROR("MQTT subscribe failed: {}", e.what());
        subscribed_ = false;
    }
}

void MqttClient::unsubscribe(const std::string& topic) {
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        pending_subscriptions_.erase(topic);
    }

    if (!connected_) {
        LOG_DEBUG("MQTT unsubscribe skipped (not connected): {}", topic);
        return;
    }

    LOG_INFO("MQTT unsubscribing from: {}", topic);

    try {
        client_->unsubscribe(topic);
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            if (pending_subscriptions_.empty()) {
                subscribed_ = false;
            }
        }
    } catch (const mqtt::exception& e) {
        LOG_ERROR("MQTT unsubscribe failed: {}", e.what());
    }
}

void MqttClient::publish(const std::string& topic, const std::string& payload) {
    if (!connected_) {
        LOG_WARN("MQTT publish dropped (not connected): {}", topic);
        return;
    }

    try {
        auto msg = mqtt::make_message(topic, payload, MQTT_QOS, false);
        client_->publish(msg);
        LOG_DEBUG("MQTT published to: {} ({} bytes)", topic, payload.size());
    } catch (const mqtt::exception& e) {
        LOG_ERROR("MQTT publish failed: {}", e.what());
    }
}

void MqttClient::setMessageCallback(MessageCallback callback) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    message_callback_ = std::move(callback);
}

bool MqttClient::isConnected() const {
    return connected_.load();
}

bool MqttClient::isSubscribed() const {
    return subscribed_.load();
}

// mqtt::callback interface implementation

void MqttClient::connected(const std::string& cause) {
    LOG_INFO("MQTT connected: {}", cause.empty() ? "initial connection" : cause);
    connected_ = true;

    // Wake up reconnect worker so it exits immediately
    reconnect_cv_.notify_all();

    // Re-subscribe to all pending subscriptions
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        for (const auto& topic : pending_subscriptions_) {
            LOG_INFO("MQTT subscribing to: {} (QoS {})", topic, MQTT_QOS);
            try {
                client_->subscribe(topic, MQTT_QOS, nullptr, *this);
            } catch (const mqtt::exception& e) {
                LOG_ERROR("MQTT subscribe failed for {}: {}", topic, e.what());
            }
        }
    }
}

void MqttClient::connection_lost(const std::string& cause) {
    LOG_WARN("MQTT connection lost: {}", cause.empty() ? "unknown" : cause);
    connected_ = false;
    subscribed_ = false;

    if (!stop_requested_) {
        scheduleReconnect();
    }
}

void MqttClient::message_arrived(mqtt::const_message_ptr msg) {
    LOG_DEBUG("MQTT message received on: {} ({} bytes)", msg->get_topic(),
              msg->get_payload().size());

    std::lock_guard<std::mutex> lock(callback_mutex_);
    if (message_callback_) {
        message_callback_(msg->get_topic(), msg->get_payload_str());
    }
}

// mqtt::iaction_listener interface implementation

void MqttClient::on_success(const mqtt::token& tok) {
    LOG_DEBUG("MQTT on_success: type={}", static_cast<int>(tok.get_type()));

    if (tok.get_type() == mqtt::token::Type::CONNECT) {
        // Note: connected() callback is also called, but log here too
        LOG_INFO("MQTT connect action successful");
    } else if (tok.get_type() == mqtt::token::Type::SUBSCRIBE) {
        LOG_INFO("MQTT subscription successful");
        subscribed_ = true;
    }
}

void MqttClient::on_failure(const mqtt::token& tok) {
    LOG_ERROR("MQTT on_failure callback entered");

    int rc = tok.get_return_code(); // Use return_code, not reason_code (v5 only)
    int msg_id = tok.get_message_id();
    int token_type = static_cast<int>(tok.get_type());
    std::string err_msg = tok.get_error_message();

    LOG_ERROR("MQTT action failed: type={}, rc={}, msg_id={}, error='{}'", token_type, rc, msg_id,
              err_msg);

    if (tok.get_type() == mqtt::token::Type::CONNECT) {
        if (!stop_requested_) {
            scheduleReconnect();
        }
    } else if (tok.get_type() == mqtt::token::Type::SUBSCRIBE) {
        subscribed_ = false;
    }
}

void MqttClient::scheduleReconnect() {
    // Check if already reconnecting (atomic, no lock needed for read)
    if (reconnecting_.load()) {
        LOG_DEBUG("Reconnect already in progress");
        return;
    }

    // Join any completed thread (must be outside lock to avoid deadlock)
    if (reconnect_thread_.joinable()) {
        LOG_DEBUG("Joining completed reconnect thread");
        reconnect_thread_.join();
    }

    std::lock_guard<std::mutex> lock(reconnect_mutex_);
    reconnect_thread_ = std::thread(&MqttClient::reconnectWorker, this);
}

void MqttClient::reconnectWorker() {
    reconnecting_ = true;

    while (!stop_requested_ && !connected_) {
        auto delay =
            calculateBackoff(reconnect_attempt_, INITIAL_BACKOFF_MS, max_reconnect_delay_s_);
        LOG_INFO("MQTT reconnecting in {}ms (attempt {})", delay.count(), reconnect_attempt_ + 1);

        {
            std::unique_lock<std::mutex> lock(reconnect_mutex_);
            if (reconnect_cv_.wait_for(
                    lock, delay, [this] { return stop_requested_.load() || connected_.load(); })) {
                break; // Stop requested or connection succeeded
            }
        }

        if (stop_requested_ || connected_) {
            break;
        }

        reconnect_attempt_++;

        try {
            client_->connect(conn_opts_, nullptr, *this);
            // Wait a bit for connection callback
            std::this_thread::sleep_for(std::chrono::milliseconds(RECONNECT_POST_CONNECT_DELAY_MS));
        } catch (const mqtt::exception& e) {
            LOG_ERROR("MQTT reconnect attempt failed: {}", e.what());
        }
    }

    // Reset counter here (owned exclusively by this thread)
    reconnect_attempt_ = 0;
    reconnecting_ = false;
}

std::chrono::milliseconds MqttClient::calculateBackoff(int attempt, int initial_ms,
                                                       int max_delay_s) {
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, then capped at max_delay_s
    int64_t cap_ms = static_cast<int64_t>(max_delay_s) * 1000;
    int64_t delay_ms = static_cast<int64_t>(initial_ms);

    for (int i = 0; i < attempt; ++i) {
        delay_ms *= 2;
        if (delay_ms >= cap_ms) {
            delay_ms = cap_ms;
            break;
        }
    }

    return std::chrono::milliseconds(delay_ms);
}

} // namespace tracker
