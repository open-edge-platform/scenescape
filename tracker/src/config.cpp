#include "config.h"
#include "simdjson.h"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unordered_set>

// Stream output operators
std::ostream& operator<<(std::ostream& os, const SslConfig& cfg) {
    os << "SSL Configuration:" << std::endl;
    os << "    Enabled: " << (cfg.enabled ? "Yes" : "No") << std::endl;
    if (cfg.enabled) {
        os << "    CA Certificate: " << cfg.ca_cert_path << std::endl;
        os << "    Client Certificate: " << cfg.client_cert_path << std::endl;
        os << "    Client Key: " << cfg.client_key_path << std::endl;
        os << "    Verify Server: " << (cfg.verify_server ? "Yes" : "No") << std::endl;
    }
    return os;
}

std::ostream& operator<<(std::ostream& os, const MqttConfig& cfg) {
    os << "MQTT Configuration:" << std::endl;
    os << "  Broker: " << cfg.server_address << std::endl;
    os << "  Client ID: " << cfg.client_id << std::endl;
    os << "  QoS: " << cfg.qos << std::endl;
    os << "  " << cfg.ssl;
    return os;
}

std::ostream& operator<<(std::ostream& os, const MetricsConfig& cfg) {
    os << "Metrics Configuration:" << std::endl;
    os << "  Enabled: " << (cfg.enabled ? "Yes" : "No") << std::endl;
    os << "  OTLP Endpoint: " << (cfg.otlp_endpoint.empty() ? "(none)" : cfg.otlp_endpoint)
       << std::endl;
    os << "  Export Interval: " << cfg.export_interval_seconds << " seconds" << std::endl;
    os << "  Service Name: " << cfg.service_name << std::endl;
    return os;
}

std::ostream& operator<<(std::ostream& os, const TracingConfig& cfg) {
    os << "Tracing Configuration:" << std::endl;
    os << "  Enabled: " << (cfg.enabled ? "Yes" : "No") << std::endl;
    os << "  OTLP Endpoint: " << (cfg.otlp_endpoint.empty() ? "(none)" : cfg.otlp_endpoint)
       << std::endl;
    os << "  Service Name: " << cfg.service_name << std::endl;
    return os;
}

std::ostream& operator<<(std::ostream& os, const LoggingConfig& cfg) {
    os << "Logging Configuration:" << std::endl;
    os << "  Level: " << cfg.level << std::endl;
    return os;
}

std::ostream& operator<<(std::ostream& os, const ScenesConfig& cfg) {
    os << "Scenes Configuration:" << std::endl;
    os << "  Source: " << cfg.source << std::endl;
    if (cfg.source == "file") {
        os << "  File Path: "
           << (cfg.file_path.empty() ? "(default)" : cfg.file_path) << std::endl;
    } else if (cfg.source == "api") {
        os << "  API Endpoint:" << std::endl;
        os << "    URL: " << cfg.api_endpoint.url << std::endl;
        os << "    Username: " << cfg.api_endpoint.username << std::endl;
        os << "    Password: " << std::string(cfg.api_endpoint.password.length(), '*') << std::endl;
        os << "    Skip SSL Verification: "
           << (cfg.api_endpoint.skip_ssl_verification ? "Yes" : "No") << std::endl;
        os << "    Reload Topic: "
           << (cfg.api_endpoint.reload_topic.empty() ? "(default: scenescape/cmd/tracker/config/reload)"
                                                     : cfg.api_endpoint.reload_topic)
           << std::endl;
        os << "    Output File: " << cfg.api_endpoint.output_file << std::endl;
    }
    return os;
}

std::ostream& operator<<(std::ostream& os, const Config& cfg) {
    os << "MQTT[server=" << cfg.mqtt.server_address << ", client=" << cfg.mqtt.client_id
       << "] ";
    os << "Scenes[source=" << cfg.scenes.source;
    if (cfg.scenes.source == "file" && !cfg.scenes.file_path.empty()) {
        os << ", file=" << cfg.scenes.file_path;
    } else if (cfg.scenes.source == "api" && !cfg.scenes.api_endpoint.url.empty()) {
        os << ", api=" << cfg.scenes.api_endpoint.url;
    }
    os << "] ";
    os << "Metrics[enabled=" << (cfg.metrics.enabled ? "yes" : "no")
       << ", otlp=" << (cfg.metrics.otlp_endpoint.empty() ? "none" : cfg.metrics.otlp_endpoint)
       << ", interval=" << cfg.metrics.export_interval_seconds << "s"
       << ", service=" << cfg.metrics.service_name << "] ";
    os << "Tracing[enabled=" << (cfg.tracing.enabled ? "yes" : "no")
       << ", otlp=" << (cfg.tracing.otlp_endpoint.empty() ? "none" : cfg.tracing.otlp_endpoint)
       << ", service=" << cfg.tracing.service_name << "] ";
    os << "Logging[level=" << cfg.logging.level << "] ";
    os << "TimeChunking[fps=" << cfg.time_chunking_fps << ", max_lag=" << cfg.max_lag_seconds
       << "s]";
    return os;
}
Config load_config_from_json(const std::string& config_path) {
    Config config;

    if (!std::filesystem::exists(config_path)) {
        throw std::runtime_error("Config file not found at: " + config_path);
    }

    try {
        // Read and parse JSON file using simdjson
        std::ifstream file(config_path);
        if (!file.is_open()) {
            throw std::runtime_error("Failed to open config file: " + config_path);
        }

        std::string json_string((std::istreambuf_iterator<char>(file)),
                                std::istreambuf_iterator<char>());

        simdjson::dom::parser parser;
        auto doc = parser.parse(json_string);

        // Extract mqtt configuration
        auto mqtt = doc["mqtt"];

        // Read client id
        config.mqtt.client_id = std::string(mqtt["client_id"]);

        // Read SSL configuration (optional)
        if (mqtt.at_key("ssl").error() == simdjson::SUCCESS) {
            auto ssl = mqtt["ssl"];
            config.mqtt.ssl.enabled = bool(ssl["enabled"]);

            if (config.mqtt.ssl.enabled) {
                config.mqtt.ssl.ca_cert_path = std::string(ssl["ca_cert_path"]);
                config.mqtt.ssl.client_cert_path = std::string(ssl["client_cert_path"]);
                config.mqtt.ssl.client_key_path = std::string(ssl["client_key_path"]);

                // verify_server defaults to true
                if (ssl.at_key("verify_server").error() == simdjson::SUCCESS) {
                    config.mqtt.ssl.verify_server = bool(ssl["verify_server"]);
                } else {
                    config.mqtt.ssl.verify_server = true;
                }
            }
        } else {
            config.mqtt.ssl.enabled = false;
            config.mqtt.ssl.verify_server = true;
        }

        // Read server address (host and port)
        std::string host = std::string(mqtt["host"]);
        std::string port = std::string(mqtt["port"]);
        std::string scheme = config.mqtt.ssl.enabled ? "ssl://" : "tcp://";
        config.mqtt.server_address = scheme + host + ":" + port;

        // Read QoS - handle both int and uint64_t
        uint64_t qos_val = mqtt["qos"];
        config.mqtt.qos = static_cast<int>(qos_val);

        // Topics removed from config schema; subscription/publish are determined internally.

        // Extract metrics configuration (with defaults if not present)
        if (doc.at_key("metrics").error() == simdjson::SUCCESS) {
            auto metrics = doc["metrics"];
            config.metrics.enabled = bool(metrics["enabled"]);
            config.metrics.export_interval_seconds =
                static_cast<int>(uint64_t(metrics["export_interval_seconds"]));

            // Required OTLP endpoint
            if (metrics.at_key("otlp_endpoint").error() == simdjson::SUCCESS) {
                config.metrics.otlp_endpoint = std::string(metrics["otlp_endpoint"]);
            } else {
                config.metrics.otlp_endpoint = "";
            }

            // Service name with default
            if (metrics.at_key("service_name").error() == simdjson::SUCCESS) {
                config.metrics.service_name = std::string(metrics["service_name"]);
            } else {
                config.metrics.service_name = "tracker-service";
            }
        } else {
            // Default values if metrics section is not present
            config.metrics.enabled = false;
            config.metrics.otlp_endpoint = "";
            config.metrics.export_interval_seconds = 10;
            config.metrics.service_name = "tracker-service";
        }

        // Extract tracing configuration (with defaults if not present)
        if (doc.at_key("tracing").error() == simdjson::SUCCESS) {
            auto tracing = doc["tracing"];
            config.tracing.enabled = bool(tracing["enabled"]);

            // Required OTLP endpoint
            if (tracing.at_key("otlp_endpoint").error() == simdjson::SUCCESS) {
                config.tracing.otlp_endpoint = std::string(tracing["otlp_endpoint"]);
            } else {
                config.tracing.otlp_endpoint = "";
            }

            // Service name with default
            if (tracing.at_key("service_name").error() == simdjson::SUCCESS) {
                config.tracing.service_name = std::string(tracing["service_name"]);
            } else {
                config.tracing.service_name = "tracker-service";
            }
        } else {
            // Default values if tracing section is not present
            config.tracing.enabled = false;
            config.tracing.otlp_endpoint = "";
            config.tracing.service_name = "tracker-service";
        }

        // Extract logging configuration (with defaults if not present)
        if (doc.at_key("logging").error() == simdjson::SUCCESS) {
            auto logging = doc["logging"];
            config.logging.level = std::string(logging["level"]);
        } else {
            // Default values if logging section is not present
            config.logging.level = "info";
        }

        // Extract scenes configuration (with defaults if not present)
        if (doc.at_key("scenes").error() == simdjson::SUCCESS) {
            auto scenes = doc["scenes"];
            
            if (scenes.at_key("source").error() == simdjson::SUCCESS) {
                config.scenes.source = std::string(scenes["source"]);
                
                // Validate source
                if (config.scenes.source != "file" && config.scenes.source != "api") {
                    throw std::runtime_error(
                        "Invalid scenes.source: '" + config.scenes.source +
                        "' (must be 'file' or 'api')");
                }
            }
            
            if (scenes.at_key("file_path").error() == simdjson::SUCCESS) {
                config.scenes.file_path = std::string(scenes["file_path"]);
            }
            
            // Parse api_endpoint config (nested under scenes)
            if (scenes.at_key("api_endpoint").error() == simdjson::SUCCESS) {
                auto api_endpoint = scenes["api_endpoint"];
                
                if (api_endpoint.at_key("url").error() == simdjson::SUCCESS) {
                    config.scenes.api_endpoint.url = std::string(api_endpoint["url"]);
                }
                
                if (api_endpoint.at_key("username").error() == simdjson::SUCCESS) {
                    config.scenes.api_endpoint.username = std::string(api_endpoint["username"]);
                }
                
                if (api_endpoint.at_key("password").error() == simdjson::SUCCESS) {
                    config.scenes.api_endpoint.password = std::string(api_endpoint["password"]);
                }
                
                if (api_endpoint.at_key("skip_ssl_verification").error() == simdjson::SUCCESS) {
                    config.scenes.api_endpoint.skip_ssl_verification =
                        bool(api_endpoint["skip_ssl_verification"]);
                } else {
                    config.scenes.api_endpoint.skip_ssl_verification = true;
                }
                
                if (api_endpoint.at_key("reload_topic").error() == simdjson::SUCCESS) {
                    config.scenes.api_endpoint.reload_topic =
                        std::string(api_endpoint["reload_topic"]);
                } else {
                    config.scenes.api_endpoint.reload_topic =
                        "scenescape/cmd/tracker/config/reload";
                }
                
                if (api_endpoint.at_key("output_file").error() == simdjson::SUCCESS) {
                    config.scenes.api_endpoint.output_file =
                        std::string(api_endpoint["output_file"]);
                } else {
                    config.scenes.api_endpoint.output_file = "config/scenes-from-api.json";
                }
            }
        } else {
            // Default to file mode
            config.scenes.source = "file";
            config.scenes.file_path = "";
        }

        // Extract time chunking configuration (with defaults if not present)
        if (doc.at_key("time_chunking_fps").error() == simdjson::SUCCESS) {
            config.time_chunking_fps = static_cast<int>(uint64_t(doc["time_chunking_fps"]));
        }

        if (doc.at_key("max_lag_seconds").error() == simdjson::SUCCESS) {
            config.max_lag_seconds = double(doc["max_lag_seconds"]);
        }

        return config;
    } catch (const std::exception& exc) {
        throw std::runtime_error("Error parsing config file: " + std::string(exc.what()));
    }
}
