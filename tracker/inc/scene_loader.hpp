// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "manager_rest_client.hpp"

#include <array>
#include <filesystem>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <rapidjson/document.h>

namespace tracker {

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
 * @brief Abstract interface for loading scene configurations.
 *
 * Implementations load scenes from different sources (file, API, etc.).
 */
class ISceneLoader {
public:
    virtual ~ISceneLoader() = default;

    /**
     * @brief Load scene configurations from the source.
     *
     * @return Vector of loaded scenes with camera configurations
     * @throws std::runtime_error if loading fails
     */
    virtual std::vector<Scene> load() = 0;
};

/**
 * @brief Create a scene loader based on configuration.
 *
 * Factory function that creates the appropriate loader implementation
 * based on the scenes.source configuration setting.
 *
 * @param config Scene source configuration
 * @param config_dir Directory containing config file (for resolving relative paths)
 * @param manager_config Manager API config (required when source=Api)
 * @param schema_dir Directory containing schema files (for API response validation)
 * @return Unique pointer to the scene loader implementation
 * @throws std::runtime_error if configuration is invalid
 */
std::unique_ptr<ISceneLoader>
create_scene_loader(const ScenesConfig& config, const std::filesystem::path& config_dir,
                    const std::optional<ManagerConfig>& manager_config = std::nullopt,
                    const std::filesystem::path& schema_dir = {});

/// Factory type for creating IManagerRestClient instances (for testability).
using ManagerClientFactory =
    std::function<std::unique_ptr<IManagerRestClient>(const ManagerConfig&)>;

/// Default factory: creates a real ManagerRestClient.
inline std::unique_ptr<IManagerRestClient> default_manager_client_factory(const ManagerConfig& c) {
    return std::make_unique<ManagerRestClient>(c.url, c.ca_cert_path);
}

// Internal factory functions used by create_scene_loader (defined in separate TUs)
std::unique_ptr<ISceneLoader>
create_api_scene_loader(const ManagerConfig& manager_config,
                        const std::filesystem::path& schema_dir,
                        ManagerClientFactory client_factory = default_manager_client_factory);

/// JSON Pointer paths (RFC6901) for scene/camera fields
namespace scene_json {
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
} // namespace scene_json

/// Internal helpers for API scene loading (exposed for testability).
namespace detail {

/// Read file contents and trim trailing whitespace.
std::string read_file_trimmed(const std::filesystem::path& path);

/// Transform a single camera from Manager API flat format to tracker schema format.
void transform_camera_to_schema(rapidjson::Value& camera,
                                rapidjson::Document::AllocatorType& alloc);

/// Transform API response scenes array to tracker schema format.
void transform_api_scenes(rapidjson::Document& doc);

/// Read username and password from JSON auth file.
std::pair<std::string, std::string> read_auth_file(const std::string& path);

/// Validate each scene in the array against a JSON schema file.
/// Returns a new document containing only the scenes that passed validation.
/// Invalid scenes are logged with a warning and skipped.
rapidjson::Document validate_scenes(const rapidjson::Document& scenes_doc,
                                    const std::filesystem::path& schema_path);

} // namespace detail

} // namespace tracker
