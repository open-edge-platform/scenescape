// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <filesystem>
#include <optional>
#include <string>

namespace tracker {

/**
 * @brief TLS/SSL certificate settings for secure connections.
 */
struct SslConfig {
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
    std::optional<SslConfig> ssl;
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
