// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_registry.hpp"

namespace tracker {

void SceneRegistry::register_scenes(const std::vector<Scene>& scenes) {
    // Clear existing registrations
    scenes_.clear();
    camera_to_scene_.clear();
    camera_to_camera_.clear();

    // Copy scenes and build mappings
    scenes_ = scenes;

    for (size_t scene_idx = 0; scene_idx < scenes_.size(); ++scene_idx) {
        const auto& scene = scenes_[scene_idx];

        for (size_t cam_idx = 0; cam_idx < scene.cameras.size(); ++cam_idx) {
            const auto& camera = scene.cameras[cam_idx];

            // Check for duplicate camera
            auto it = camera_to_scene_.find(camera.uid);
            if (it != camera_to_scene_.end()) {
                const auto& existing_scene = scenes_[it->second];
                throw DuplicateCameraError(camera.uid, existing_scene.name, scene.name);
            }

            camera_to_scene_[camera.uid] = scene_idx;
            camera_to_camera_[camera.uid] = cam_idx;
        }
    }
}

const Scene* SceneRegistry::find_scene_for_camera(const std::string& camera_id) const {
    auto it = camera_to_scene_.find(camera_id);
    if (it == camera_to_scene_.end()) {
        return nullptr;
    }
    return &scenes_[it->second];
}

const Camera* SceneRegistry::find_camera(const std::string& camera_id) const {
    auto scene_it = camera_to_scene_.find(camera_id);
    if (scene_it == camera_to_scene_.end()) {
        return nullptr;
    }

    auto cam_it = camera_to_camera_.find(camera_id);
    if (cam_it == camera_to_camera_.end()) {
        return nullptr;
    }

    return &scenes_[scene_it->second].cameras[cam_it->second];
}

std::vector<std::string>
SceneRegistry::get_camera_ids_for_scene(const std::string& scene_id) const {
    std::vector<std::string> camera_ids;

    for (const auto& scene : scenes_) {
        if (scene.uid == scene_id) {
            for (const auto& camera : scene.cameras) {
                camera_ids.push_back(camera.uid);
            }
            break;
        }
    }

    return camera_ids;
}

std::vector<std::string> SceneRegistry::get_all_camera_ids() const {
    std::vector<std::string> camera_ids;
    camera_ids.reserve(camera_to_scene_.size());

    for (const auto& [camera_id, _] : camera_to_scene_) {
        camera_ids.push_back(camera_id);
    }

    return camera_ids;
}

} // namespace tracker
