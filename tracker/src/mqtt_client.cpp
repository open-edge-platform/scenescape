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
constexpr int KEEPALIVE_SECONDS = 60;
constexpr int CONNECT_TIMEOUT_SECONDS = 10;
constexpr int DISCONNECT_WAIT_MS = 500;

std::string getHostname() {
    char hostname[HOSTNAME_BUFFER_SIZE];
    if (gethostname(hostname, sizeof(hostname)) == 0) {
        hostname[HOSTNAME_BUFFER_SIZE - 1] = '\0';
        return std::string(hostname);
    }
    return "unknown";
}

/**
 * @brief Clear proxy environment variables if they are set but empty.
 *
 * Paho MQTT library workaround: Paho reads proxy environment variables
 * (http_proxy, https_proxy, etc.) but fails when they are set to empty
 * strings - it attempts to use "" as a proxy URL, causing connection errors.
 *
 * This commonly occurs when:
 *   - Docker containers set proxy vars to empty to override host values
 *   - Makefile targets export empty proxy vars for local development
 *
 * Solution: Detect empty proxy vars and unset them entirely, while
 * preserving real proxy URLs for production environments that need them.
 */
void clearEmptyProxyVars() {
    const char* proxy_vars[] = {"http_proxy",  "HTTP_PROXY", "https_proxy",
                                "HTTPS_PROXY", "no_proxy",   "NO_PROXY"};

    bool cleared_any = false;
    for (const char* var : proxy_vars) {
        const char* value = std::getenv(var);
        if (value != nullptr && value[0] == '\0') {
            unsetenv(var);
            cleared_any = true;
        }
    }

    if (cleared_any) {
        LOG_DEBUG("Cleared empty proxy environment variables");
    }
}

} // namespace

std::string MqttClient::generateClientId() {
    return "tracker-" + getHostname() + "-" + std::to_string(getpid());
}

bool MqttClient::isRetryableConnectError(int rc) {
    // MQTT v3.1.1 CONNACK return codes that indicate permanent failures
    switch (rc) {
        case 1: // Unacceptable protocol version
        case 2: // Identifier rejected
        case 4: // Bad user name or password
        case 5: // Not authorized
            return false;
        default:
            return true; // 0=success, 3=server unavailable, negatives=transient
    }
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
    // Paho handles post-connection reconnection automatically with exponential backoff
    // (1s min, max_reconnect_delay_s max). Our connected() callback re-subscribes
    // topics on reconnect. Initial connect failures cause the process to exit;
    // the container orchestrator (Docker restart: always, K8s) handles restart.
    // This works because docker-compose depends_on ensures broker starts first.
    auto conn_opts_builder = mqtt::connect_options_builder()
                                 .clean_session(true)
                                 .automatic_reconnect(std::chrono::seconds(1),
                                                      std::chrono::seconds(max_reconnect_delay_s_))
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
        LOG_ERROR("MQTT connect failed: {} (rc={})", e.what(), e.get_reason_code());
        exit_code_ = 1; // Sync failures are network errors — always retryable
        throw;
    } catch (const std::exception& e) {
        LOG_ERROR("MQTT connect failed: {}", e.what());
        exit_code_ = 1;
        throw;
    }
}

void MqttClient::disconnect(std::chrono::milliseconds drain_timeout) {
    // Guard against double-disconnect
    if (stop_requested_.exchange(true)) {
        LOG_DEBUG("MQTT disconnect already in progress or completed");
        return;
    }

    LOG_INFO("MQTT disconnecting (drain timeout: {}ms)", drain_timeout.count());

    // Wait for any in-flight Paho callbacks to complete before disabling them.
    // This prevents use-after-free if a callback is mid-execution when we destroy members.
    while (callbacks_in_flight_.load() > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    if (client_) {
        // Disable callbacks to prevent Paho from invoking them after we're destroyed.
        // This is critical because Paho may invoke connection_lost or other callbacks
        // on internal threads even after disconnect() completes.
        client_->disable_callbacks();

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

    try {
        client_->subscribe(topic, MQTT_QOS, nullptr, *this);
        LOG_DEBUG_ENTRY(LogEntry("MQTT subscribe request queued")
                            .component("mqtt")
                            .mqtt({.topic = topic, .direction = "subscribe"}));
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
    withGuard([&] {
        LOG_INFO_ENTRY(LogEntry("MQTT connected")
                           .component("mqtt")
                           .operation(cause.empty() ? "initial connection" : cause));
        connected_ = true;

        // Re-subscribe to all pending subscriptions
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            for (const auto& topic : pending_subscriptions_) {
                try {
                    client_->subscribe(topic, MQTT_QOS, nullptr, *this);
                    LOG_DEBUG_ENTRY(LogEntry("MQTT subscribe request queued")
                                        .component("mqtt")
                                        .mqtt({.topic = topic, .direction = "subscribe"}));
                } catch (const mqtt::exception& e) {
                    LOG_ERROR("MQTT subscribe failed for {}: {}", topic, e.what());
                }
            }
        }
    });
}

void MqttClient::connection_lost(const std::string& cause) {
    withGuard([&] {
        LOG_WARN("MQTT connection lost: {}", cause.empty() ? "unknown" : cause);
        connected_ = false;
        subscribed_ = false;
        LOG_INFO("Paho auto-reconnect will attempt to restore connection");
    });
}

void MqttClient::message_arrived(mqtt::const_message_ptr msg) {
    withGuard([&] {
        LOG_DEBUG_ENTRY(LogEntry("MQTT message received")
                            .component("mqtt")
                            .mqtt({.topic = msg->get_topic(), .direction = "receive"}));

        std::lock_guard<std::mutex> lock(callback_mutex_);
        if (message_callback_) {
            message_callback_(msg->get_topic(), msg->get_payload_str());
        }
    });
}

// mqtt::iaction_listener interface implementation

void MqttClient::on_success(const mqtt::token& tok) {
    withGuard([&] {
        if (tok.get_type() == mqtt::token::Type::CONNECT) {
            // Note: connected() callback already logs, skip duplicate here
            LOG_DEBUG("MQTT connect token completed");
        } else if (tok.get_type() == mqtt::token::Type::SUBSCRIBE) {
            // Get topics from token (Paho stores them on subscribe tokens)
            auto topics = tok.get_topics();
            if (topics && !topics->empty()) {
                for (const auto& topic : *topics) {
                    LOG_INFO_ENTRY(LogEntry("MQTT subscription successful")
                                       .component("mqtt")
                                       .mqtt({.topic = topic, .direction = "subscribe"}));
                }
            } else {
                LOG_INFO_ENTRY(LogEntry("MQTT subscription successful").component("mqtt"));
            }
            subscribed_ = true;
        }
    });
}

void MqttClient::on_failure(const mqtt::token& tok) {
    withGuard([&] {
        int rc = tok.get_return_code(); // Use return_code, not reason_code (v5 only)
        int msg_id = tok.get_message_id();
        int token_type = static_cast<int>(tok.get_type());
        std::string err_msg = tok.get_error_message();

        LOG_ERROR("MQTT action failed: type={}, rc={}, msg_id={}, error='{}'", token_type, rc,
                  msg_id, err_msg);

        if (tok.get_type() == mqtt::token::Type::CONNECT) {
            bool retryable = isRetryableConnectError(rc);
            exit_code_ = retryable ? 1 : 0;
            LOG_ERROR("MQTT connect failed (rc={}) — {} — process will exit with code {}", rc,
                      retryable ? "retryable" : "non-retryable (auth/protocol)", exit_code_.load());
        } else if (tok.get_type() == mqtt::token::Type::SUBSCRIBE) {
            subscribed_ = false;
        }
    });
}

} // namespace tracker
