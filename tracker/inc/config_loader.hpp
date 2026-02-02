// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

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
 * @brief Camera intrinsic parameters.
 */
struct CameraIntrinsics {
    double fx = 0.0; ///< Focal length X (pixels)
    double fy = 0.0; ///< Focal length Y (pixels)
    double cx = 0.0; ///< Principal point X (pixels)
    double cy = 0.0; ///< Principal point Y (pixels)
};

/**
 * @brief Lens distortion coefficients.
 */
struct CameraDistortion {
    double k1 = 0.0;
    double k2 = 0.0;
    double p1 = 0.0;
    double p2 = 0.0;
};

/**
 * @brief Camera configuration with calibration data.
 */
struct Camera {
    std::string uid;  ///< Camera identifier (matches MQTT topic camera_id)
    std::string name; ///< Human-readable camera name
    CameraIntrinsics intrinsics;
    CameraDistortion distortion;
};

/**
 * @brief Scene configuration with assigned cameras.
 */
struct Scene {
    std::string uid;             ///< Scene identifier (UUID, used in MQTT topic)
    std::string name;            ///< Human-readable scene name
    std::vector<Camera> cameras; ///< Cameras assigned to this scene
};

/**
 * @brief Scene configuration source settings.
 */
struct ScenesConfig {
    std::string source = "inline"; ///< "inline" or "api"
    std::vector<Scene> data;       ///< Scene data (populated when source="inline")
};

/**
 * @brief Service configuration loaded from JSON config file.
 *
 * Values can be overridden by environment variables with TRACKER_ prefix.
 */
struct ServiceConfig {
    InfrastructureConfig infrastructure;
    ObservabilityConfig observability;
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

// Scenes
constexpr char SCENES_SOURCE[] = "/scenes/source";
constexpr char SCENES_DATA[] = "/scenes/data";

// Scene fields (relative pointers within scene object)
constexpr char SCENE_UID[] = "/uid";
constexpr char SCENE_NAME[] = "/name";
constexpr char SCENE_CAMERAS[] = "/cameras";

// Camera fields (relative pointers within camera object)
constexpr char CAMERA_UID[] = "/uid";
constexpr char CAMERA_NAME[] = "/name";
constexpr char CAMERA_INTRINSICS_FX[] = "/intrinsics/fx";
constexpr char CAMERA_INTRINSICS_FY[] = "/intrinsics/fy";
constexpr char CAMERA_INTRINSICS_CX[] = "/intrinsics/cx";
constexpr char CAMERA_INTRINSICS_CY[] = "/intrinsics/cy";
constexpr char CAMERA_DISTORTION_K1[] = "/distortion/k1";
constexpr char CAMERA_DISTORTION_K2[] = "/distortion/k2";
constexpr char CAMERA_DISTORTION_P1[] = "/distortion/p1";
constexpr char CAMERA_DISTORTION_P2[] = "/distortion/p2";
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
