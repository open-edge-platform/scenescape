// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
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
 * @brief Lens distortion coefficients.
 */
struct CameraDistortion {
    double k1 = 0.0; ///< Radial distortion coefficient k1
    double k2 = 0.0; ///< Radial distortion coefficient k2
    double p1 = 0.0; ///< Tangential distortion coefficient p1
    double p2 = 0.0; ///< Tangential distortion coefficient p2
};

/**
 * @brief Camera intrinsic parameters (internal camera model).
 */
struct CameraIntrinsics {
    double fx = 0.0;             ///< Focal length X (pixels)
    double fy = 0.0;             ///< Focal length Y (pixels)
    double cx = 0.0;             ///< Principal point X (pixels)
    double cy = 0.0;             ///< Principal point Y (pixels)
    CameraDistortion distortion; ///< Lens distortion coefficients
};

/**
 * @brief Camera extrinsic parameters (pose in world coordinates).
 *
 * Defines camera position and orientation in the scene coordinate system.
 * Matches Python controller's CameraPose class in scene_common/src/scene_common/transform.py.
 *
 * @note Rotation uses Euler angles in XYZ order (degrees), matching:
 *       scipy.spatial.transform.Rotation.from_euler('XYZ', rotation, degrees=True)
 */
struct CameraExtrinsics {
    std::array<double, 3> translation = {0.0, 0.0, 0.0}; ///< Position [x, y, z] in meters
    std::array<double, 3> rotation = {0.0, 0.0, 0.0};    ///< Euler angles [X, Y, Z] in degrees
    std::array<double, 3> scale = {1.0, 1.0, 1.0};       ///< Scale factors [x, y, z]
};

/**
 * @brief Camera configuration with calibration data.
 */
struct Camera {
    std::string uid;             ///< Camera identifier (matches MQTT topic camera_id)
    std::string name;            ///< Human-readable camera name
    CameraIntrinsics intrinsics; ///< Intrinsic parameters (including distortion)
    CameraExtrinsics extrinsics; ///< Extrinsic parameters (pose in world)
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
 * @brief Scene configuration source type.
 */
enum class SceneSource {
    File, ///< Load scenes from external JSON file (scenes.file_path)
    Api   ///< Fetch scenes from Manager REST API (not yet implemented)
};

/**
 * @brief Scene configuration source settings.
 */
struct ScenesConfig {
    SceneSource source = SceneSource::File; ///< Scene source type
    std::optional<std::string> file_path;   ///< Path to scene file (when source=File)
    std::vector<Scene> data;                ///< Parsed scene data
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
constexpr char SCENES_FILE_PATH[] = "/scenes/file_path";

// Scene fields (relative pointers within scene object)
constexpr char SCENE_UID[] = "/uid";
constexpr char SCENE_NAME[] = "/name";
constexpr char SCENE_CAMERAS[] = "/cameras";

// Camera fields (relative pointers within camera object)
constexpr char CAMERA_UID[] = "/uid";
constexpr char CAMERA_NAME[] = "/name";

// Camera intrinsics fields (nested under /intrinsics)
constexpr char CAMERA_INTRINSICS_FX[] = "/intrinsics/fx";
constexpr char CAMERA_INTRINSICS_FY[] = "/intrinsics/fy";
constexpr char CAMERA_INTRINSICS_CX[] = "/intrinsics/cx";
constexpr char CAMERA_INTRINSICS_CY[] = "/intrinsics/cy";
constexpr char CAMERA_INTRINSICS_DISTORTION_K1[] = "/intrinsics/distortion/k1";
constexpr char CAMERA_INTRINSICS_DISTORTION_K2[] = "/intrinsics/distortion/k2";
constexpr char CAMERA_INTRINSICS_DISTORTION_P1[] = "/intrinsics/distortion/p1";
constexpr char CAMERA_INTRINSICS_DISTORTION_P2[] = "/intrinsics/distortion/p2";

// Camera extrinsics fields (nested under /extrinsics)
constexpr char CAMERA_EXTRINSICS_TRANSLATION[] = "/extrinsics/translation";
constexpr char CAMERA_EXTRINSICS_ROTATION[] = "/extrinsics/rotation";
constexpr char CAMERA_EXTRINSICS_SCALE[] = "/extrinsics/scale";
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
