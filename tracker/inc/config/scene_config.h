#pragma once

#include <iostream>
#include <string>
#include <vector>

struct CameraIntrinsics {
    double fx; // focal length x
    double fy; // focal length y
    double cx; // principal point x
    double cy; // principal point y
};

struct CameraDistortion {
    double k1; // radial distortion coefficient 1
    double k2; // radial distortion coefficient 2
    double p1; // tangential distortion coefficient 1
    double p2; // tangential distortion coefficient 2
};

struct CameraConfig {
    std::string id;
    std::string name;
    CameraIntrinsics intrinsics;
    CameraDistortion distortion;
};

struct SceneConfig {
    std::string id;
    std::string name;
    std::vector<std::string> camera_ids;
};

struct SceneConfiguration {
    std::vector<CameraConfig> cameras;
    std::vector<SceneConfig> scenes;
};

// Stream output operators
std::ostream& operator<<(std::ostream& os, const CameraIntrinsics& intrinsics);
std::ostream& operator<<(std::ostream& os, const CameraDistortion& distortion);
std::ostream& operator<<(std::ostream& os, const CameraConfig& cam);
std::ostream& operator<<(std::ostream& os, const SceneConfig& scene);
std::ostream& operator<<(std::ostream& os, const SceneConfiguration& cfg);

/**
 * Load scene configuration from JSON file
 * @param config_path Path to the JSON configuration file
 * @return SceneConfiguration struct with loaded cameras and scenes
 */
SceneConfiguration load_scene_config_from_json(const std::string& config_path);

/**
 * Load scene configuration with fallback to environment variable or default path
 * @return SceneConfiguration struct with loaded values
 */
SceneConfiguration load_scene_config();

/**
 * Validate scene configuration
 * @param config SceneConfiguration to validate
 * @throws std::runtime_error if validation fails
 */
void validate_scene_config(const SceneConfiguration& config);
