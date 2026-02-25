// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_loader.hpp"

#include "config_loader.hpp"
#include "logger.hpp"
#include "scene_parser.hpp"

#include <fstream>
#include <stdexcept>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/schema.h>
#include <rapidjson/stringbuffer.h>

namespace tracker {
namespace detail {

std::string read_file_trimmed(const std::filesystem::path& path) {
    std::ifstream ifs(path);
    if (!ifs.is_open()) {
        throw std::runtime_error("Failed to open file: " + path.string());
    }
    std::string content((std::istreambuf_iterator<char>(ifs)), std::istreambuf_iterator<char>());
    auto end = content.find_last_not_of(" \t\n\r");
    if (end != std::string::npos) {
        content.erase(end + 1);
    }
    return content;
}

void transform_camera_to_schema(rapidjson::Value& camera,
                                rapidjson::Document::AllocatorType& alloc) {
    // Build extrinsics object from flat camera fields
    if (!camera.HasMember("extrinsics")) {
        rapidjson::Value extrinsics(rapidjson::kObjectType);

        if (camera.HasMember("translation") && camera["translation"].IsArray()) {
            rapidjson::Value arr(camera["translation"], alloc);
            extrinsics.AddMember("translation", arr, alloc);
        }
        if (camera.HasMember("rotation") && camera["rotation"].IsArray()) {
            rapidjson::Value arr(camera["rotation"], alloc);
            extrinsics.AddMember("rotation", arr, alloc);
        }
        if (camera.HasMember("scale") && camera["scale"].IsArray()) {
            rapidjson::Value arr(camera["scale"], alloc);
            extrinsics.AddMember("scale", arr, alloc);
        }

        camera.AddMember("extrinsics", extrinsics, alloc);
    }

    // Move distortion inside intrinsics if it's at camera root level
    if (camera.HasMember("distortion") && !camera.HasMember("intrinsics")) {
        rapidjson::Value intrinsics(rapidjson::kObjectType);
        rapidjson::Value dist(camera["distortion"], alloc);
        intrinsics.AddMember("distortion", dist, alloc);
        camera.AddMember("intrinsics", intrinsics, alloc);
    } else if (camera.HasMember("distortion") && camera.HasMember("intrinsics")) {
        if (!camera["intrinsics"].HasMember("distortion")) {
            rapidjson::Value dist(camera["distortion"], alloc);
            camera["intrinsics"].AddMember("distortion", dist, alloc);
        }
    }
}

void transform_api_scenes(rapidjson::Document& doc) {
    auto& alloc = doc.GetAllocator();

    if (!doc.IsArray())
        return;

    for (auto& scene_val : doc.GetArray()) {
        if (scene_val.HasMember("cameras") && scene_val["cameras"].IsArray()) {
            for (auto& cam_val : scene_val["cameras"].GetArray()) {
                transform_camera_to_schema(cam_val, alloc);
            }
        }
    }
}

std::pair<std::string, std::string> read_auth_file(const std::string& path) {
    std::string content = read_file_trimmed(path);

    rapidjson::Document doc;
    doc.Parse(content.c_str());

    if (doc.HasParseError() || !doc.IsObject()) {
        throw std::runtime_error("Auth file is not valid JSON: " + path);
    }

    if (!doc.HasMember("user") || !doc["user"].IsString()) {
        throw std::runtime_error("Auth file missing 'user' field: " + path);
    }
    if (!doc.HasMember("password") || !doc["password"].IsString()) {
        throw std::runtime_error("Auth file missing 'password' field: " + path);
    }

    return {doc["user"].GetString(), doc["password"].GetString()};
}

rapidjson::Document validate_scenes(const rapidjson::Document& scenes_doc,
                                    const std::filesystem::path& schema_path) {
    if (!scenes_doc.IsArray()) {
        throw std::runtime_error("validate_scenes: input must be a JSON array");
    }

    std::ifstream ifs(schema_path);
    if (!ifs.is_open()) {
        throw std::runtime_error("Failed to open scene schema: " + schema_path.string());
    }

    rapidjson::IStreamWrapper isw(ifs);
    rapidjson::Document schema_doc;
    schema_doc.ParseStream(isw);
    if (schema_doc.HasParseError()) {
        throw std::runtime_error("Failed to parse scene schema: " + schema_path.string());
    }

    rapidjson::SchemaDocument schema(schema_doc);

    rapidjson::Document valid_scenes;
    valid_scenes.SetArray();
    auto& alloc = valid_scenes.GetAllocator();

    int scene_index = 0;
    for (const auto& scene_val : scenes_doc.GetArray()) {
        rapidjson::SchemaValidator validator(schema);
        if (!scene_val.Accept(validator)) {
            rapidjson::StringBuffer sb;
            validator.GetInvalidSchemaPointer().StringifyUriFragment(sb);

            std::string scene_id = "index " + std::to_string(scene_index);
            if (scene_val.HasMember("name") && scene_val["name"].IsString()) {
                scene_id = "'" + std::string(scene_val["name"].GetString()) + "'";
            }

            LOG_WARN("Skipping scene {} — validation failed at: {}, keyword: {}", scene_id,
                     sb.GetString(), validator.GetInvalidSchemaKeyword());
        } else {
            rapidjson::Value scene_copy(scene_val, alloc);
            valid_scenes.PushBack(scene_copy, alloc);
        }
        ++scene_index;
    }

    return valid_scenes;
}

} // namespace detail

namespace {

class ApiSceneLoader : public ISceneLoader {
public:
    ApiSceneLoader(ManagerConfig manager_config, std::filesystem::path schema_dir,
                   ManagerClientFactory client_factory)
        : manager_config_(std::move(manager_config)), schema_dir_(std::move(schema_dir)),
          client_factory_(std::move(client_factory)) {}

    std::vector<Scene> load() override {
        // Read credentials from auth file
        auto [username, password] = detail::read_auth_file(manager_config_.auth_path);

        // Authenticate and fetch scenes
        auto client = client_factory_(manager_config_);
        client->authenticate(username, password);
        std::string response_body = client->fetchScenes();

        // Parse the API response
        rapidjson::Document response_doc;
        response_doc.Parse(response_body.c_str());
        if (response_doc.HasParseError()) {
            throw std::runtime_error("Failed to parse Manager API response at offset " +
                                     std::to_string(response_doc.GetErrorOffset()));
        }

        if (!response_doc.IsObject() || !response_doc.HasMember("results") ||
            !response_doc["results"].IsArray()) {
            throw std::runtime_error("Manager API response missing 'results' array");
        }

        // Extract results array into a new document for transformation
        rapidjson::Document scenes_doc;
        scenes_doc.SetArray();
        auto& alloc = scenes_doc.GetAllocator();
        for (const auto& scene_val : response_doc["results"].GetArray()) {
            rapidjson::Value scene_copy(scene_val, alloc);
            scenes_doc.PushBack(scene_copy, alloc);
        }

        // Transform flat API format -> nested schema format
        detail::transform_api_scenes(scenes_doc);

        // Validate each scene against scene.schema.json (skips invalid scenes with warning)
        auto scene_schema_path = schema_dir_ / "scene.schema.json";
        auto valid_scenes = detail::validate_scenes(scenes_doc, scene_schema_path);

        // Parse validated scenes into structs
        std::vector<Scene> scenes;
        for (const auto& scene_val : valid_scenes.GetArray()) {
            scenes.push_back(detail::parse_scene(scene_val));
        }

        LOG_INFO("Loaded {} scenes from Manager API", scenes.size());
        return scenes;
    }

private:
    ManagerConfig manager_config_;
    std::filesystem::path schema_dir_;
    ManagerClientFactory client_factory_;
};

} // namespace

std::unique_ptr<ISceneLoader> create_api_scene_loader(const ManagerConfig& manager_config,
                                                      const std::filesystem::path& schema_dir,
                                                      ManagerClientFactory client_factory) {
    return std::make_unique<ApiSceneLoader>(manager_config, schema_dir, std::move(client_factory));
}

} // namespace tracker
