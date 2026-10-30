// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "scenes_config.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

#include <rapidjson/fwd.h>

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
 * @brief NTP server connection settings.
 */
constexpr int kDefaultNtpSyncIntervalS = 300;

struct NtpConfig {
    std::string server;                             ///< NTP server hostname or IP
    int sync_interval_s = kDefaultNtpSyncIntervalS; ///< Re-sync interval in seconds
};

/**
 * @brief OTLP collector connection settings.
 */
struct OtlpConfig {
    std::string endpoint; ///< OTLP gRPC endpoint (e.g., localhost:4317)
    bool insecure = true; ///< Use insecure (non-TLS) connection
};

/**
 * @brief External service connections.
 */
struct InfrastructureConfig {
    MqttConfig mqtt;
    TrackerConfig tracker;
    std::optional<NtpConfig> ntp;         ///< Optional NTP clock synchronisation
    std::optional<ManagerConfig> manager; ///< Required when scenes.source='api'
    std::optional<OtlpConfig> otlp;       ///< Required when metrics or tracing enabled
};

/**
 * @brief Logging configuration.
 */
struct LoggingConfig {
    std::string level = "info";
};

/**
 * @brief Metrics export configuration.
 */
struct MetricsConfig {
    bool enabled = false;       ///< Enable OpenTelemetry metrics export
    int export_interval_s = 60; ///< Export interval in seconds
};

/**
 * @brief Tracing configuration.
 */
struct TracingConfig {
    bool enabled = false;      ///< Enable OpenTelemetry distributed tracing
    int export_interval_s = 5; ///< Batch span processor schedule delay in seconds
};

/**
 * @brief Observability settings.
 */
struct ObservabilityConfig {
    LoggingConfig logging;
    MetricsConfig metrics;
    TracingConfig tracing;
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
/// PTZ PoseContext consumption mode; both flags off means Off.
enum class PtzMode {
    Off,
    Enforce,
    Shadow
};

inline constexpr const char* kDefaultPtzShadowRunId = "unspecified";
constexpr int kDefaultPtzShadowSampleEveryN = 10;
inline constexpr const char* kDefaultPtzAssignmentsPath =
    "/scenescape/config/positioning-assignments.json";

struct PtzShadowConfig {
    std::string run_id = kDefaultPtzShadowRunId;        ///< Joins records into one run artifact
    int sample_every_n = kDefaultPtzShadowSampleEveryN; ///< Record every Nth decision per source
    bool per_decision = false; ///< Sampled JSONL records instead of the summary log line
};

/**
 * @brief PTZ PoseContext consumer settings (see tracker-ptz-pose-consumption.md).
 *
 * The four deployment-owned bounds have no defaults; they are required and validated only
 * when enabled or shadow_mode is set.
 */
struct PtzConfig {
    bool enabled = false;     ///< Gate PTZ batches with the dwell contract, project with the pose
    bool shadow_mode = false; ///< Observe and record only; tracking is unchanged
    std::optional<double> max_pose_age_s;
    std::optional<double> max_clock_offset_s;
    std::optional<double> max_detection_pipeline_latency_s;
    std::optional<double> max_detection_timestamp_uncertainty_s;
    std::string assignments_path = kDefaultPtzAssignmentsPath;
    PtzShadowConfig shadow;

    [[nodiscard]] PtzMode mode() const {
        if (enabled) {
            return PtzMode::Enforce;
        }
        return shadow_mode ? PtzMode::Shadow : PtzMode::Off;
    }
};

struct ServiceConfig {
    InfrastructureConfig infrastructure;
    ObservabilityConfig observability;
    TrackingConfig tracking;
    ScenesConfig scenes;
    PtzConfig ptz;
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

// NTP
constexpr char INFRASTRUCTURE_NTP[] = "/infrastructure/ntp";
constexpr char INFRASTRUCTURE_NTP_SERVER[] = "/infrastructure/ntp/server";
constexpr char INFRASTRUCTURE_NTP_SYNC_INTERVAL_S[] = "/infrastructure/ntp/sync_interval_s";

// Manager
constexpr char INFRASTRUCTURE_MANAGER[] = "/infrastructure/manager";
constexpr char INFRASTRUCTURE_MANAGER_URL[] = "/infrastructure/manager/url";
constexpr char INFRASTRUCTURE_MANAGER_AUTH_PATH[] = "/infrastructure/manager/auth_path";
constexpr char INFRASTRUCTURE_MANAGER_CA_CERT_PATH[] = "/infrastructure/manager/ca_cert_path";

// OTLP
constexpr char INFRASTRUCTURE_OTLP[] = "/infrastructure/otlp";
constexpr char INFRASTRUCTURE_OTLP_ENDPOINT[] = "/infrastructure/otlp/endpoint";
constexpr char INFRASTRUCTURE_OTLP_INSECURE[] = "/infrastructure/otlp/insecure";

// Observability - Metrics
constexpr char OBSERVABILITY_METRICS_ENABLED[] = "/observability/metrics/enabled";
constexpr char OBSERVABILITY_METRICS_EXPORT_INTERVAL_S[] =
    "/observability/metrics/export_interval_s";

// Observability - Tracing
constexpr char OBSERVABILITY_TRACING_ENABLED[] = "/observability/tracing/enabled";
constexpr char OBSERVABILITY_TRACING_EXPORT_INTERVAL_S[] =
    "/observability/tracing/export_interval_s";

// Scenes
constexpr char SCENES_SOURCE[] = "/scenes/source";
constexpr char SCENES_FILE_PATH[] = "/scenes/file_path";

// PTZ PoseContext consumption
constexpr char PTZ_ENABLED[] = "/ptz/enabled";
constexpr char PTZ_SHADOW_MODE[] = "/ptz/shadow_mode";
constexpr char PTZ_MAX_POSE_AGE_S[] = "/ptz/max_pose_age_s";
constexpr char PTZ_MAX_CLOCK_OFFSET_S[] = "/ptz/max_clock_offset_s";
constexpr char PTZ_MAX_DETECTION_PIPELINE_LATENCY_S[] = "/ptz/max_detection_pipeline_latency_s";
constexpr char PTZ_MAX_DETECTION_TIMESTAMP_UNCERTAINTY_S[] =
    "/ptz/max_detection_timestamp_uncertainty_s";
constexpr char PTZ_ASSIGNMENTS_PATH[] = "/ptz/assignments_path";
constexpr char PTZ_SHADOW_RUN_ID[] = "/ptz/shadow/run_id";
constexpr char PTZ_SHADOW_SAMPLE_EVERY_N[] = "/ptz/shadow/sample_every_n";
constexpr char PTZ_SHADOW_PER_DECISION[] = "/ptz/shadow/per_decision";
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

namespace detail {
/// Read the ptz block of a schema-valid config document (defaults when absent).
void load_ptz_section(const rapidjson::Document& config_doc, PtzConfig& ptz);
/// Apply TRACKER_PTZ_* environment overrides. @throws std::runtime_error on invalid values
void apply_ptz_env_overrides(PtzConfig& ptz);
/// Validate an active PTZ configuration. @throws std::runtime_error when unusable
void validate_ptz_config(const ServiceConfig& config);
} // namespace detail

} // namespace tracker
