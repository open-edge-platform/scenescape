// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_loader.hpp"

#include "scene_parser.hpp"

#include <fstream>
#include <stdexcept>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>

namespace tracker {

namespace {

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
            scenes.push_back(detail::parse_scene(scene_val));
        }

        return scenes;
    }

private:
    std::filesystem::path file_path_;
};

} // namespace

std::unique_ptr<ISceneLoader>
create_scene_loader(const ScenesConfig& config, const std::filesystem::path& config_dir,
                    const std::optional<ManagerConfig>& manager_config,
                    const std::filesystem::path& schema_dir) {
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

        case SceneSource::Api: {
            if (!manager_config.has_value()) {
                throw std::runtime_error("Manager config is required when scenes.source='api'");
            }
            if (schema_dir.empty()) {
                throw std::runtime_error(
                    "Missing required config: scenes.schema_dir (required when "
                    "scenes.source='api')");
            }
            return create_api_scene_loader(*manager_config, schema_dir);
        }
    }

    throw std::runtime_error("Unknown scene source type");
}

} // namespace tracker
