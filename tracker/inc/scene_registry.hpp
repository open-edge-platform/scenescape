// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"

#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace tracker {

/**
 * @brief Exception thrown when a camera is registered to multiple scenes.
 */
class DuplicateCameraError : public std::runtime_error {
public:
    DuplicateCameraError(const std::string& camera_id, const std::string& scene1,
                         const std::string& scene2)
        : std::runtime_error("Camera '" + camera_id + "' is assigned to multiple scenes: '" +
                             scene1 + "' and '" + scene2 + "'"),
          camera_id_(camera_id), scene1_(scene1), scene2_(scene2) {}

    [[nodiscard]] const std::string& camera_id() const { return camera_id_; }
    [[nodiscard]] const std::string& scene1() const { return scene1_; }
    [[nodiscard]] const std::string& scene2() const { return scene2_; }

private:
    std::string camera_id_;
    std::string scene1_;
    std::string scene2_;
};

/**
 * @brief Registry for camera-to-scene mapping.
 *
 * Provides fast lookup of scene information for incoming camera messages.
 * Enforces that each camera belongs to exactly one scene.
 */
class SceneRegistry {
public:
    /**
     * @brief Register scenes and build camera-to-scene mapping.
     *
     * @param scenes Vector of scene configurations
     * @throws DuplicateCameraError if a camera is assigned to multiple scenes
     */
    void register_scenes(const std::vector<Scene>& scenes);

    /**
     * @brief Find the scene that a camera belongs to.
     *
     * @param camera_id Camera identifier from MQTT topic
     * @return Pointer to scene or nullptr if camera is not registered
     */
    [[nodiscard]] const Scene* find_scene_for_camera(const std::string& camera_id) const;

    /**
     * @brief Find a specific camera by ID.
     *
     * @param camera_id Camera identifier
     * @return Pointer to camera or nullptr if not found
     */
    [[nodiscard]] const Camera* find_camera(const std::string& camera_id) const;

    /**
     * @brief Get all registered scenes.
     *
     * @return Vector of all scenes
     */
    [[nodiscard]] const std::vector<Scene>& get_all_scenes() const { return scenes_; }

    /**
     * @brief Get camera IDs for a specific scene.
     *
     * @param scene_id Scene identifier
     * @return Vector of camera IDs belonging to the scene (empty if scene not found)
     */
    [[nodiscard]] std::vector<std::string>
    get_camera_ids_for_scene(const std::string& scene_id) const;

    /**
     * @brief Get all registered camera IDs.
     *
     * @return Vector of all camera IDs across all scenes
     */
    [[nodiscard]] std::vector<std::string> get_all_camera_ids() const;

    /**
     * @brief Check if registry has any scenes registered.
     */
    [[nodiscard]] bool empty() const { return scenes_.empty(); }

    /**
     * @brief Get total number of registered cameras.
     */
    [[nodiscard]] size_t camera_count() const { return camera_to_scene_.size(); }

    /**
     * @brief Get total number of registered scenes.
     */
    [[nodiscard]] size_t scene_count() const { return scenes_.size(); }

private:
    std::vector<Scene> scenes_;
    std::unordered_map<std::string, size_t> camera_to_scene_;  // camera_id -> scene index
    std::unordered_map<std::string, size_t> camera_to_camera_; // camera_id -> camera index in scene
};

} // namespace tracker
