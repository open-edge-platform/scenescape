// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <filesystem>
#include <optional>
#include <string>

namespace tracker {

/**
 * @brief TLS certificate settings for secure connections.
 */
struct TlsConfig {
    std::string ca_cert_path;
    std::string client_cert_path;
    std::string client_key_path;
    bool verify_server = true;
};

/**
 * @brief MQTT broker connection settings.
 */
struct MqttConfig {
    std::string host;
    int port;
    bool insecure = false;
    std::optional<TlsConfig> tls;
};

/**
 * @brief Health check HTTP server settings.
 */
struct HealthcheckConfig {
    int port = 8080;
};

/**
 * @brief Tracker service settings.
 */
struct TrackerConfig {
    HealthcheckConfig healthcheck;
    bool schema_validation = true;
};

/**
 * @brief External service connections.
 */
struct InfrastructureConfig {
    MqttConfig mqtt;
    TrackerConfig tracker;
};

/**
 * @brief Logging configuration.
 */
struct LoggingConfig {
    std::string level = "info";
};

/**
 * @brief Observability settings.
 */
struct ObservabilityConfig {
    LoggingConfig logging;
};

/**
 * @brief Service configuration loaded from JSON config file.
 *
 * Values can be overridden by environment variables with TRACKER_ prefix.
 */
struct ServiceConfig {
    InfrastructureConfig infrastructure;
    ObservabilityConfig observability;
};

/// JSON Pointer paths (RFC6901) for extracting ServiceConfig values
namespace json {
constexpr char OBSERVABILITY_LOGGING_LEVEL[] = "/observability/logging/level";
constexpr char INFRASTRUCTURE_TRACKER_HEALTHCHECK_PORT[] =
    "/infrastructure/tracker/healthcheck/port";
constexpr char INFRASTRUCTURE_TRACKER_SCHEMA_VALIDATION[] =
    "/infrastructure/tracker/schema_validation";
constexpr char INFRASTRUCTURE_MQTT_HOST[] = "/infrastructure/mqtt/host";
constexpr char INFRASTRUCTURE_MQTT_PORT[] = "/infrastructure/mqtt/port";
constexpr char INFRASTRUCTURE_MQTT_INSECURE[] = "/infrastructure/mqtt/insecure";
constexpr char INFRASTRUCTURE_MQTT_TLS[] = "/infrastructure/mqtt/tls";
constexpr char INFRASTRUCTURE_MQTT_TLS_CA_CERT_PATH[] = "/infrastructure/mqtt/tls/ca_cert_path";
constexpr char INFRASTRUCTURE_MQTT_TLS_CLIENT_CERT_PATH[] =
    "/infrastructure/mqtt/tls/client_cert_path";
constexpr char INFRASTRUCTURE_MQTT_TLS_CLIENT_KEY_PATH[] =
    "/infrastructure/mqtt/tls/client_key_path";
constexpr char INFRASTRUCTURE_MQTT_TLS_VERIFY_SERVER[] = "/infrastructure/mqtt/tls/verify_server";
} // namespace json

/**
 * @brief Load and validate service configuration from JSON file.
 *
 * Configuration layering (priority: high to low):
 * 1. Environment variables (TRACKER_LOG_LEVEL, TRACKER_HEALTHCHECK_PORT)
 * 2. JSON configuration file
 *
 * @param config_path Path to the JSON configuration file
 * @param schema_path Path to the JSON schema file
 * @return ServiceConfig Validated configuration
 *
 * @throws std::runtime_error if config file not found, invalid JSON, or schema validation fails
 */
ServiceConfig load_config(const std::filesystem::path& config_path,
                          const std::filesystem::path& schema_path);

} // namespace tracker
