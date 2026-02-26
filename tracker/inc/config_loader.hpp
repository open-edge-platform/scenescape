// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "scenes_config.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

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
 * @brief Manager REST API connection settings.
 */
struct ManagerConfig {
    std::string url;                         ///< Manager API base URL
    std::string auth_path;                   ///< Path to JSON auth file {user, password}
    std::optional<std::string> ca_cert_path; ///< CA cert for HTTPS verification
};

/**
 * @brief External service connections.
 */
struct InfrastructureConfig {
    MqttConfig mqtt;
    TrackerConfig tracker;
    std::optional<ManagerConfig> manager; ///< Required when scenes.source='api'
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
 * @brief Tracking algorithm parameters.
 */
constexpr double kDefaultMaxLagS = 1.0;
constexpr int kDefaultTimeChunkingRateFps = 15;
constexpr int kDefaultMaxWorkers = 50;

// RobotVision tracker parameter defaults
constexpr double kDefaultMaxUnreliableTimeS = 1.0;
constexpr double kDefaultNonMeasurementTimeDynamicS = 0.8;
constexpr double kDefaultNonMeasurementTimeStaticS = 1.6;

struct TrackingConfig {
    double max_lag_s = kDefaultMaxLagS; ///< Max lag for detection frames (seconds)
    int time_chunking_rate_fps =
        kDefaultTimeChunkingRateFps;      ///< Chunk dispatch rate (frames per second)
    int max_workers = kDefaultMaxWorkers; ///< DoS protection: max worker threads (scene+category)

    // RobotVision tracker parameters
    double max_unreliable_time_s = kDefaultMaxUnreliableTimeS; ///< Max time track can be unreliable
    double non_measurement_time_dynamic_s =
        kDefaultNonMeasurementTimeDynamicS; ///< Time before dynamic track dropped
    double non_measurement_time_static_s =
        kDefaultNonMeasurementTimeStaticS; ///< Time before static track dropped
};

/**
 * @brief Service configuration loaded from JSON config file.
 *
 * Values can be overridden by environment variables with TRACKER_ prefix.
 */
struct ServiceConfig {
    InfrastructureConfig infrastructure;
    ObservabilityConfig observability;
    TrackingConfig tracking;
    ScenesConfig scenes;
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

// Tracking
constexpr char TRACKING_MAX_LAG_S[] = "/tracking/max_lag_s";
constexpr char TRACKING_TIME_CHUNKING_RATE_FPS[] = "/tracking/time_chunking_rate_fps";
constexpr char TRACKING_MAX_WORKERS[] = "/tracking/max_workers";
constexpr char TRACKING_MAX_UNRELIABLE_TIME_S[] = "/tracking/max_unreliable_time_s";
constexpr char TRACKING_NON_MEASUREMENT_TIME_DYNAMIC_S[] =
    "/tracking/non_measurement_time_dynamic_s";
constexpr char TRACKING_NON_MEASUREMENT_TIME_STATIC_S[] = "/tracking/non_measurement_time_static_s";

// Manager
constexpr char INFRASTRUCTURE_MANAGER[] = "/infrastructure/manager";
constexpr char INFRASTRUCTURE_MANAGER_URL[] = "/infrastructure/manager/url";
constexpr char INFRASTRUCTURE_MANAGER_AUTH_PATH[] = "/infrastructure/manager/auth_path";
constexpr char INFRASTRUCTURE_MANAGER_CA_CERT_PATH[] = "/infrastructure/manager/ca_cert_path";

// Scenes
constexpr char SCENES_SOURCE[] = "/scenes/source";
constexpr char SCENES_FILE_PATH[] = "/scenes/file_path";
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
