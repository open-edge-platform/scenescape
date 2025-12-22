#include "config/scene_config.h"
#include "simdjson.h"
#include "config/config_validation.hpp"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unordered_set>

const std::string DFLT_SCENE_CONFIG_PATH{"config/scenes.json"};

// Stream output operators
std::ostream& operator<<(std::ostream& os, const CameraIntrinsics& intrinsics) {
    os << "fx=" << intrinsics.fx << ", fy=" << intrinsics.fy << ", cx=" << intrinsics.cx
       << ", cy=" << intrinsics.cy;
    return os;
}

std::ostream& operator<<(std::ostream& os, const CameraDistortion& distortion) {
    os << "k1=" << distortion.k1 << ", k2=" << distortion.k2 << ", p1=" << distortion.p1
       << ", p2=" << distortion.p2;
    return os;
}

std::ostream& operator<<(std::ostream& os, const CameraConfig& cam) {
    os << "Camera: " << cam.id << " (" << cam.name << ")" << std::endl;
    os << "  Intrinsics: " << cam.intrinsics << std::endl;
    os << "  Distortion: " << cam.distortion;
    return os;
}

std::ostream& operator<<(std::ostream& os, const SceneConfig& scene) {
    os << "Scene: " << scene.id << " (" << scene.name << ")" << std::endl;
    os << "  Cameras: [";
    for (size_t i = 0; i < scene.camera_ids.size(); ++i) {
        os << scene.camera_ids[i];
        if (i < scene.camera_ids.size() - 1) {
            os << ", ";
        }
    }
    os << "]";
    return os;
}

std::ostream& operator<<(std::ostream& os, const SceneConfiguration& cfg) {
    os << "SceneConfiguration[";
    os << "Cameras[count=" << cfg.cameras.size();
    for (size_t i = 0; i < cfg.cameras.size(); ++i) {
        os << ", cam" << (i + 1) << "=" << cfg.cameras[i].name;
    }
    os << "] ";
    os << "Scenes[count=" << cfg.scenes.size();
    for (size_t i = 0; i < cfg.scenes.size(); ++i) {
        os << ", scene" << (i + 1) << "=" << cfg.scenes[i].name;
    }
    os << "]";
    return os;
}

void validate_scene_config(const SceneConfiguration& config) {
    // Validate at least one scene exists
    if (config.scenes.empty()) {
        throw std::runtime_error("Configuration must contain at least one scene");
    }

    // Validate camera-to-scene mapping (each camera must belong to exactly one scene)
    std::unordered_set<std::string> cameras_in_scenes;
    for (const auto& scene : config.scenes) {
        for (const auto& camera_id : scene.camera_ids) {
            // Check for duplicate camera across scenes
            if (cameras_in_scenes.count(camera_id)) {
                throw std::runtime_error("Camera '" + camera_id +
                                         "' is assigned to multiple scenes");
            }
            cameras_in_scenes.insert(camera_id);

            // Verify camera exists in cameras array
            bool found = false;
            for (const auto& cam : config.cameras) {
                if (cam.id == camera_id) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                throw std::runtime_error("Scene '" + scene.name + "' references unknown camera '" +
                                         camera_id + "'");
            }
        }
    }

    // Warn about orphaned cameras (configured but not in any scene)
    for (const auto& camera : config.cameras) {
        if (!cameras_in_scenes.count(camera.id)) {
            std::cerr << "WARNING: Camera '" << camera.id
                      << "' is configured but not assigned to any scene" << std::endl;
        }
    }
}

SceneConfiguration load_scene_config_from_json(const std::string& config_path) {
    SceneConfiguration config;

    if (!std::filesystem::exists(config_path)) {
        throw std::runtime_error("Scene config file not found at: " + config_path);
    }

    try {
        // Validate against schema if present
        const std::string schema_path = "config/scenes.schema.json";
        if (std::filesystem::exists(schema_path)) {
            config_schema::validate_json_file_against_schema(config_path, schema_path);
        }

        // Read and parse JSON file using simdjson
        std::ifstream file(config_path);
        if (!file.is_open()) {
            throw std::runtime_error("Failed to open scene config file: " + config_path);
        }

        std::string json_string((std::istreambuf_iterator<char>(file)),
                                std::istreambuf_iterator<char>());

        simdjson::dom::parser parser;
        auto doc = parser.parse(json_string);

        // Extract camera configuration array
        auto cameras_array = doc["cameras"].get_array();

        for (auto camera_elem : cameras_array) {
            CameraConfig camera;

            camera.id = std::string(camera_elem["id"]);
            camera.name = std::string(camera_elem["name"]);

            // Extract intrinsics
            auto intrinsics = camera_elem["intrinsics"];
            camera.intrinsics.fx = double(intrinsics["fx"]);
            camera.intrinsics.fy = double(intrinsics["fy"]);
            camera.intrinsics.cx = double(intrinsics["cx"]);
            camera.intrinsics.cy = double(intrinsics["cy"]);

            // Extract distortion
            auto distortion = camera_elem["distortion"];
            camera.distortion.k1 = double(distortion["k1"]);
            camera.distortion.k2 = double(distortion["k2"]);
            camera.distortion.p1 = double(distortion["p1"]);
            camera.distortion.p2 = double(distortion["p2"]);

            config.cameras.push_back(camera);
        }

        // Extract scenes configuration array
        if (doc.at_key("scenes").error() == simdjson::SUCCESS) {
            auto scenes_array = doc["scenes"].get_array();

            for (auto scene_elem : scenes_array) {
                SceneConfig scene;

                scene.id = std::string(scene_elem["id"]);
                scene.name = std::string(scene_elem["name"]);

                // Extract camera IDs array
                auto cameras = scene_elem["cameras"].get_array();
                for (auto camera_id : cameras) {
                    scene.camera_ids.push_back(std::string(camera_id));
                }

                config.scenes.push_back(scene);
            }
        } else {
            throw std::runtime_error("Configuration missing required 'scenes' section");
        }

        // Validate the configuration
        validate_scene_config(config);

        return config;
    } catch (const std::exception& exc) {
        throw std::runtime_error("Error parsing scene config file: " + std::string(exc.what()));
    }
}

SceneConfiguration load_scene_config() {
    // Use default path only
    return load_scene_config_from_json(DFLT_SCENE_CONFIG_PATH);
}
