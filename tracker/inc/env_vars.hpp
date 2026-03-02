// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

// -----------------------------------------------------------------------------
// Environment variable names for runtime configuration overrides.
//
// These constants provide a single source of truth for environment variable
// names used to override configuration file values at runtime.
// -----------------------------------------------------------------------------

namespace tracker::env {

/// trace|debug|info|warn|error
constexpr const char* LOG_LEVEL = "TRACKER_LOG_LEVEL";

/// 1024-65535
constexpr const char* HEALTHCHECK_PORT = "TRACKER_HEALTHCHECK_PORT";

constexpr const char* MQTT_HOST = "TRACKER_MQTT_HOST";

/// 1-65535
constexpr const char* MQTT_PORT = "TRACKER_MQTT_PORT";

/// true|false
constexpr const char* MQTT_INSECURE = "TRACKER_MQTT_INSECURE";

constexpr const char* MQTT_TLS_CA_CERT = "TRACKER_MQTT_TLS_CA_CERT";

constexpr const char* MQTT_TLS_CLIENT_CERT = "TRACKER_MQTT_TLS_CLIENT_CERT";

constexpr const char* MQTT_TLS_CLIENT_KEY = "TRACKER_MQTT_TLS_CLIENT_KEY";

/// true|false
constexpr const char* MQTT_TLS_VERIFY_SERVER = "TRACKER_MQTT_TLS_VERIFY_SERVER";

/// true|false
constexpr const char* MQTT_SCHEMA_VALIDATION = "TRACKER_MQTT_SCHEMA_VALIDATION";

// Tracking overrides

/// seconds, >= 0
constexpr const char* MAX_LAG_S = "TRACKER_MAX_LAG_S";

/// 1-60 FPS
constexpr const char* TIME_CHUNKING_RATE_FPS = "TRACKER_TIME_CHUNKING_RATE_FPS";

/// >= 1
constexpr const char* MAX_WORKERS = "TRACKER_MAX_WORKERS";

/// seconds, >= 0 - RobotVision tracker parameter
constexpr const char* MAX_UNRELIABLE_TIME_S = "TRACKER_MAX_UNRELIABLE_TIME_S";

/// seconds, >= 0 - RobotVision tracker parameter
constexpr const char* NON_MEASUREMENT_TIME_DYNAMIC_S = "TRACKER_NON_MEASUREMENT_TIME_DYNAMIC_S";

/// seconds, >= 0 - RobotVision tracker parameter
constexpr const char* NON_MEASUREMENT_TIME_STATIC_S = "TRACKER_NON_MEASUREMENT_TIME_STATIC_S";

// Manager API overrides

/// Manager API base URL
constexpr const char* MANAGER_URL = "TRACKER_MANAGER_URL";

/// Path to JSON auth file {user, password}
constexpr const char* MANAGER_AUTH_PATH = "TRACKER_MANAGER_AUTH_PATH";

/// Path to CA certificate for HTTPS verification
constexpr const char* MANAGER_CA_CERT_PATH = "TRACKER_MANAGER_CA_CERT_PATH";

// Scenes overrides

/// "file"|"api"
constexpr const char* SCENES_SOURCE = "TRACKER_SCENES_SOURCE";

constexpr const char* SCENES_FILE_PATH = "TRACKER_SCENES_FILE_PATH";

// Observability overrides

/// OTLP gRPC endpoint (e.g., localhost:4317)
constexpr const char* OTLP_ENDPOINT = "TRACKER_OTLP_ENDPOINT";

/// true|false
constexpr const char* METRICS_ENABLED = "TRACKER_METRICS_ENABLED";

/// true|false
constexpr const char* TRACING_ENABLED = "TRACKER_TRACING_ENABLED";

/// seconds, >= 1
constexpr const char* METRICS_EXPORT_INTERVAL_S = "TRACKER_METRICS_EXPORT_INTERVAL_S";

/// seconds, >= 1
constexpr const char* TRACING_EXPORT_INTERVAL_S = "TRACKER_TRACING_EXPORT_INTERVAL_S";

} // namespace tracker::env
