#pragma once

#include <iostream>
#include <string>
#include <vector>

struct SslConfig {
    bool enabled = false;
    std::string ca_cert_path;
    std::string client_cert_path;
    std::string client_key_path;
    bool verify_server = true;
};

struct MqttConfig {
    std::string client_id;
    std::string server_address;
    int qos;
    SslConfig ssl;
};

struct MetricsConfig {
    bool enabled;
    std::string otlp_endpoint; // OTLP endpoint (e.g., "http://localhost:4318")
    int export_interval_seconds;
    std::string service_name; // Service name for metrics
};

struct TracingConfig {
    bool enabled;
    std::string otlp_endpoint; // OTLP endpoint (e.g., "http://localhost:4318")
    std::string service_name;  // Service name for traces
};

struct LoggingConfig {
    std::string level;
};

struct ScenesConfig {
    std::string source = "file";  // "file" or "api"
    std::string file_path;        // Path for file mode (only used if source="file")
    
    // API endpoint config (only used if source="api")
    struct {
        std::string url;
        std::string username;
        std::string password;
        bool skip_ssl_verification = true;
        std::string reload_topic;
        std::string output_file;
    } api_endpoint;
};

struct Config {
    MqttConfig mqtt;
    MetricsConfig metrics;
    TracingConfig tracing;
    LoggingConfig logging;
    ScenesConfig scenes;
    int time_chunking_fps = 15;
    double max_lag_seconds = 1.0;
};

// Stream output operators
std::ostream& operator<<(std::ostream& os, const SslConfig& cfg);
std::ostream& operator<<(std::ostream& os, const MqttConfig& cfg);
std::ostream& operator<<(std::ostream& os, const MetricsConfig& cfg);
std::ostream& operator<<(std::ostream& os, const TracingConfig& cfg);
std::ostream& operator<<(std::ostream& os, const LoggingConfig& cfg);
std::ostream& operator<<(std::ostream& os, const ScenesConfig& cfg);
std::ostream& operator<<(std::ostream& os, const Config& cfg);

/**
 * Load configuration from JSON file
 * @param config_path Path to the JSON configuration file
 * @return Config struct with loaded values or defaults if file not found/invalid
 */
Config load_config_from_json(const std::string& config_path);
