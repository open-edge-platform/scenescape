#include "mqtt_client.h"
#include "logger.h"
#include "mqtt/async_client.h"
#include "mqtt/ssl_options.h"
#include "simdjson.h"
#include "trace_manager.h"
#include <chrono>
#include <iostream>
#include <quill/LogMacros.h>
#include <sstream>

#include <opentelemetry/trace/scope.h>
#include <opentelemetry/trace/span.h>
#include <opentelemetry/trace/span_startoptions.h>

class MqttClient::Impl {
public:
    Impl(const std::string& server_address, const std::string& client_id)
        : server_address_(server_address), client_id_(client_id),
          client_(server_address, client_id), callback_handler_(this), connected_(false),
          ssl_enabled_(false) {
        client_.set_callback(callback_handler_);
    }

    Impl(const std::string& server_address, const std::string& client_id,
         const SslConfig& ssl_config)
        : server_address_(server_address), client_id_(client_id),
          client_(server_address, client_id), callback_handler_(this), connected_(false),
          ssl_enabled_(ssl_config.enabled), ssl_config_(ssl_config) {
        client_.set_callback(callback_handler_);
    }

    ~Impl() {
        if (connected_) {
            try {
                disconnect();
            } catch (...) {
                // Ignore exceptions in destructor
            }
        }
    }

    void connect() {
        auto connOptsBuilder = mqtt::connect_options_builder().clean_session(true);

        if (ssl_enabled_) {
            LOG_INFO(logger::get_logger(), "Configuring SSL/TLS connection...");
            auto sslopts = mqtt::ssl_options_builder()
                               .trust_store(ssl_config_.ca_cert_path)
                               .key_store(ssl_config_.client_cert_path)
                               .private_key(ssl_config_.client_key_path)
                               .enable_server_cert_auth(ssl_config_.verify_server)
                               .finalize();
            connOptsBuilder.ssl(sslopts);
        }

        auto connOpts = connOptsBuilder.finalize();

        LOG_INFO(logger::get_logger(), "Connecting to the MQTT broker at {}...", server_address_);
        mqtt::token_ptr conntok = client_.connect(connOpts);
        conntok->wait();
        LOG_INFO(logger::get_logger(), "Connected successfully");
        connected_ = true;
    }

    void disconnect() {
        if (connected_) {
            std::cout << "\nDisconnecting..." << std::flush;
            client_.disconnect()->wait();
            std::cout << "OK" << std::endl;
            connected_ = false;
        }
    }

    void subscribe(const std::string& topic, int qos) {
        LOG_INFO(logger::get_logger(), "Subscribing to topic '{}'...", topic);
        client_.subscribe(topic, qos)->wait();
        LOG_INFO(logger::get_logger(), "Subscribed successfully");
    }

    void subscribe(const std::vector<std::string>& topics, int qos) {
        if (topics.empty()) {
            LOG_WARNING(logger::get_logger(), "No topics provided for subscription");
            return;
        }

        LOG_INFO(logger::get_logger(), "Subscribing to {} topics...", topics.size());
        for (const auto& topic : topics) {
            LOG_INFO(logger::get_logger(), "  - Subscribing to topic '{}'...", topic);
            client_.subscribe(topic, qos)->wait();
        }
        LOG_INFO(logger::get_logger(), "Successfully subscribed to all {} topics", topics.size());
    }

    void unsubscribe(const std::string& topic) {
        LOG_INFO(logger::get_logger(), "Unsubscribing from topic '{}'...", topic);
        client_.unsubscribe(topic)->wait();
        LOG_INFO(logger::get_logger(), "Unsubscribed successfully");
    }

    void unsubscribe(const std::vector<std::string>& topics) {
        if (topics.empty()) {
            LOG_WARNING(logger::get_logger(), "No topics provided for unsubscription");
            return;
        }

        LOG_INFO(logger::get_logger(), "Unsubscribing from {} topics...", topics.size());
        for (const auto& topic : topics) {
            LOG_INFO(logger::get_logger(), "  - Unsubscribing from topic '{}'...", topic);
            client_.unsubscribe(topic)->wait();
        }
        LOG_INFO(logger::get_logger(), "Successfully unsubscribed from all {} topics",
                 topics.size());
    }

    void publish(const std::string& topic, const UnregulatedTrackMsg& msg, int qos) {
        // Serialize message to JSON using the toJson() method
        std::string json = msg.toJson();

        auto pubmsg = mqtt::make_message(topic, json);
        pubmsg->set_qos(qos);

        try {
            // Publish asynchronously - don't wait for completion
            client_.publish(pubmsg);

            auto* logger = logger::get_logger();
            if (logger->get_log_level() <= quill::LogLevel::TraceL1) {
                LOG_TRACE_L1(logger, "TX topic '{}' payload: '{}'", topic, json);
            } else {
                LOG_DEBUG(logger, "TX topic '{}' with {} objects", topic, msg.objects.size());
            }
        } catch (const mqtt::exception& e) {
            LOG_ERROR(logger::get_logger(), "MQTT publish error: {}", e.what());
            throw;
        }
    }

    void set_message_callback(MessageCallback callback) { message_callback_ = callback; }

    bool is_connected() const { return connected_; }

private:
    class CallbackHandler : public virtual mqtt::callback {
    public:
        CallbackHandler(Impl* impl) : impl_(impl) {}

        void connection_lost(const std::string& cause) override {
            if (!cause.empty()) {
                LOG_WARNING(logger::get_logger(), "Connection lost: {}", cause);
            } else {
                LOG_WARNING(logger::get_logger(), "Connection lost");
            }
            impl_->connected_ = false;
        }

        void message_arrived(mqtt::const_message_ptr msg) override {
            auto& traceManager = TraceManager::getInstance();

            // Create root span for MQTT message receipt
            opentelemetry::nostd::shared_ptr<opentelemetry::trace::Span> mqtt_span;
            opentelemetry::trace::StartSpanOptions span_options;

            if (traceManager.isEnabled()) {
                auto tracer = traceManager.getTracer();
                mqtt_span = tracer->StartSpan("mqtt_message_received");
                mqtt_span->SetAttribute("mqtt.topic", msg->get_topic());
                mqtt_span->SetAttribute("mqtt.payload_size",
                                        static_cast<int64_t>(msg->to_string().size()));
                span_options.parent = mqtt_span->GetContext();
            }

            // Child span: JSON deserialization
            opentelemetry::nostd::shared_ptr<opentelemetry::trace::Span> parse_span;
            if (traceManager.isEnabled()) {
                auto tracer = traceManager.getTracer();
                parse_span = tracer->StartSpan("deserialize_detection_message", span_options);
            }

            auto parse_start = std::chrono::steady_clock::now();

            // Parse JSON with simdjson
            simdjson::dom::element doc;
            auto error = parser_.parse(msg->to_string()).get(doc);

            if (error) {
                LOG_ERROR(logger::get_logger(), "Error parsing JSON: {}",
                          simdjson::error_message(error));
                if (parse_span) {
                    parse_span->SetAttribute("error", true);
                    parse_span->SetAttribute("error.message", simdjson::error_message(error));
                    parse_span->End();
                }
                if (mqtt_span) {
                    mqtt_span->SetAttribute("error", true);
                    mqtt_span->End();
                }
                return;
            }

            CameraDetectionMsg message = CameraDetectionMsg::parse(doc);

            auto parse_end = std::chrono::steady_clock::now();
            auto parse_duration_ms =
                std::chrono::duration_cast<std::chrono::nanoseconds>(parse_end - parse_start)
                    .count() /
                1e6;

            if (parse_span) {
                parse_span->SetAttribute("camera.id", message.id);
                parse_span->SetAttribute("objects.count",
                                         static_cast<int64_t>(message.persons.size()));
                parse_span->SetAttribute("duration_ms", parse_duration_ms);
                parse_span->End();
            }

            auto* logger = logger::get_logger();
            if (logger->get_log_level() <= quill::LogLevel::TraceL1) {
                LOG_TRACE_L1(logger, "RX topic '{}' payload: '{}'", msg->get_topic(),
                             msg->to_string());
            } else {
                LOG_DEBUG(logger, "RX topic '{}' with {} objects", msg->get_topic(),
                          message.persons.size());
            }

            // Child span: Handler callback
            // Use Scope to make this span active so that spans created in the callback
            // will automatically become children of this span
            opentelemetry::nostd::shared_ptr<opentelemetry::trace::Span> callback_span;
            if (traceManager.isEnabled()) {
                auto tracer = traceManager.getTracer();
                callback_span = tracer->StartSpan("handle_detection", span_options);

                // Make this span active for the duration of the callback
                {
                    auto scope = tracer->WithActiveSpan(callback_span);

                    // Call user-defined callback if set
                    if (impl_->message_callback_) {
                        impl_->message_callback_(message);
                    }
                }

                callback_span->End();
            } else {
                // Tracing disabled, just call callback
                if (impl_->message_callback_) {
                    impl_->message_callback_(message);
                }
            }

            if (mqtt_span) {
                mqtt_span->SetAttribute("camera.id", message.id);
                mqtt_span->End();
            }
        }

        void delivery_complete(mqtt::delivery_token_ptr token) override {
            // No-op for now
        }

    private:
        Impl* impl_;
        simdjson::dom::parser parser_;
    };

    std::string server_address_;
    std::string client_id_;
    mqtt::async_client client_;
    CallbackHandler callback_handler_;
    MessageCallback message_callback_;
    bool connected_;
    bool ssl_enabled_;
    SslConfig ssl_config_;
};

// MqttClient public interface implementation

MqttClient::MqttClient(const std::string& server_address, const std::string& client_id)
    : pImpl_(std::make_unique<Impl>(server_address, client_id)) {}

MqttClient::MqttClient(const std::string& server_address, const std::string& client_id,
                       const SslConfig& ssl_config)
    : pImpl_(std::make_unique<Impl>(server_address, client_id, ssl_config)) {}

MqttClient::~MqttClient() = default;

void MqttClient::connect() {
    pImpl_->connect();
}

void MqttClient::disconnect() {
    pImpl_->disconnect();
}

void MqttClient::subscribe(const std::string& topic, int qos) {
    pImpl_->subscribe(topic, qos);
}

void MqttClient::subscribe(const std::vector<std::string>& topics, int qos) {
    pImpl_->subscribe(topics, qos);
}

void MqttClient::unsubscribe(const std::string& topic) {
    pImpl_->unsubscribe(topic);
}

void MqttClient::unsubscribe(const std::vector<std::string>& topics) {
    pImpl_->unsubscribe(topics);
}

void MqttClient::publish(const std::string& topic, const UnregulatedTrackMsg& msg, int qos) {
    pImpl_->publish(topic, msg, qos);
}

void MqttClient::set_message_callback(MessageCallback callback) {
    pImpl_->set_message_callback(callback);
}

bool MqttClient::is_connected() const {
    return pImpl_->is_connected();
}
