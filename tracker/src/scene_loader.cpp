// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_loader.hpp"

#include "json_utils.hpp"

#include <array>
#include <fstream>
#include <stdexcept>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/pointer.h>

namespace tracker {

namespace {

using Pointer = rapidjson::Pointer;
using detail::get_value;
using detail::require_value;

/**
 * @brief Get required JSON array by pointer.
 */
const rapidjson::Value::ConstArray require_array(const rapidjson::Value& doc, const char* pointer,
                                                 const std::string& context) {
    if (auto* val = Pointer(pointer).Get(doc)) {
        if (val->IsArray()) {
            return val->GetArray();
        }
    }
    throw std::runtime_error("Missing required " + context + " array: " + pointer);
}

/**
 * @brief Get required 3-element array from JSON.
 */
std::array<double, 3> require_array3(const rapidjson::Value& doc, const char* pointer,
                                     const std::string& context) {
    if (auto* val = Pointer(pointer).Get(doc)) {
        if (val->IsArray() && val->Size() == 3) {
            std::array<double, 3> result;
            for (size_t i = 0; i < 3; ++i) {
                if (!(*val)[i].IsNumber()) {
                    throw std::runtime_error(context + ": " + pointer + "[" + std::to_string(i) +
                                             "] must be a number");
                }
                result[i] = (*val)[i].GetDouble();
            }
            return result;
        }
    }
    throw std::runtime_error("Missing required " + context + " array: " + pointer);
}

/**
 * @brief Scene loader that reads from a JSON file.
 */
class FileSceneLoader : public ISceneLoader {
public:
    explicit FileSceneLoader(std::filesystem::path file_path) : file_path_(std::move(file_path)) {}

    std::vector<Scene> load() override {
        std::ifstream ifs(file_path_);
        if (!ifs.is_open()) {
            throw std::runtime_error("Failed to open scene file: " + file_path_.string());
        }

        rapidjson::IStreamWrapper isw(ifs);
        rapidjson::Document doc;
        doc.ParseStream(isw);

        if (doc.HasParseError()) {
            throw std::runtime_error("Failed to parse scene JSON: " + file_path_.string() +
                                     " at offset " + std::to_string(doc.GetErrorOffset()));
        }

        if (!doc.IsArray()) {
            throw std::runtime_error("Scene file must contain a JSON array of scenes: " +
                                     file_path_.string());
        }

        std::vector<Scene> scenes;
        for (const auto& scene_val : doc.GetArray()) {
            Scene scene;
            scene.uid = require_value<std::string>(scene_val, scene_json::SCENE_UID, "scene");
            scene.name = require_value<std::string>(scene_val, scene_json::SCENE_NAME, "scene");

            for (const auto& cam_val :
                 require_array(scene_val, scene_json::SCENE_CAMERAS, "scene")) {
                Camera camera;
                camera.uid = require_value<std::string>(cam_val, scene_json::CAMERA_UID, "camera");
                camera.name =
                    require_value<std::string>(cam_val, scene_json::CAMERA_NAME, "camera");

                // Parse intrinsics (optional, default to 0.0)
                camera.intrinsics.fx =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_FX).value_or(0.0);
                camera.intrinsics.fy =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_FY).value_or(0.0);
                camera.intrinsics.cx =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_CX).value_or(0.0);
                camera.intrinsics.cy =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_CY).value_or(0.0);

                // Parse distortion (optional, default to 0.0)
                camera.intrinsics.distortion.k1 =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_K1)
                        .value_or(0.0);
                camera.intrinsics.distortion.k2 =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_K2)
                        .value_or(0.0);
                camera.intrinsics.distortion.p1 =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_P1)
                        .value_or(0.0);
                camera.intrinsics.distortion.p2 =
                    get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_P2)
                        .value_or(0.0);

                // Parse extrinsics (required)
                std::string cam_context = "camera '" + camera.uid + "'";
                camera.extrinsics.translation =
                    require_array3(cam_val, scene_json::CAMERA_EXTRINSICS_TRANSLATION, cam_context);
                camera.extrinsics.rotation =
                    require_array3(cam_val, scene_json::CAMERA_EXTRINSICS_ROTATION, cam_context);
                camera.extrinsics.scale =
                    require_array3(cam_val, scene_json::CAMERA_EXTRINSICS_SCALE, cam_context);

                scene.cameras.push_back(std::move(camera));
            }

            scenes.push_back(std::move(scene));
        }

        return scenes;
    }

private:
    std::filesystem::path file_path_;
};

/**
 * @brief Scene loader that fetches from Manager REST API.
 */
class ApiSceneLoader : public ISceneLoader {
public:
    std::vector<Scene> load() override {
        throw std::runtime_error("API scene loading is not yet implemented");
    }
};

} // namespace

std::unique_ptr<ISceneLoader> create_scene_loader(const ScenesConfig& config,
                                                  const std::filesystem::path& config_dir) {
    switch (config.source) {
        case SceneSource::File: {
            if (!config.file_path.has_value()) {
                throw std::runtime_error("Missing required config: scenes.file_path (required when "
                                         "scenes.source='file')");
            }

            std::filesystem::path scene_file_path(*config.file_path);
            if (!scene_file_path.is_absolute()) {
                scene_file_path = config_dir / scene_file_path;
            }

            return std::make_unique<FileSceneLoader>(scene_file_path);
        }

        case SceneSource::Api:
            return std::make_unique<ApiSceneLoader>();
    }

    throw std::runtime_error("Unknown scene source type");
}

} // namespace tracker
