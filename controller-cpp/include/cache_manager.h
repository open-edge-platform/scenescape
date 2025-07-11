#pragma once

#include <string>
#include <memory>
#include <unordered_map>
#include <nlohmann/json.hpp>
#include "scene.h"
#include "rest_client.h"

namespace scenescape {

class CacheManager {
public:
    CacheManager(
        const std::string& rest_url,
        const std::string& rest_auth,
        const std::string& root_cert,
        const nlohmann::json& tracker_config_data
    );
    
    ~CacheManager() = default;

    // Scene management
    void refreshScenes();
    Scene* getSceneByUID(const std::string& uid);
    Scene* getSceneByCameraID(const std::string& camera_id);
    Scene* getSceneBySensorID(const std::string& sensor_id);
    
    // Asset management
    nlohmann::json getAssets();
    nlohmann::json getChildScenes(const std::string& scene_uid);
    
    // Camera parameter management
    void refreshScenesForCamParams(const nlohmann::json& camera_data);
    void updateCamera(const nlohmann::json& camera_data);
    bool cameraParametersChanged(const nlohmann::json& camera_data, const std::string& param_type);
    
    // Cache validation
    bool needsRefresh() const;
    double getLastRefreshTime() const { return cache_refreshed_; }

private:
    // REST client
    std::unique_ptr<RestClient> rest_client_;
    
    // Configuration
    nlohmann::json tracker_config_data_;
    
    // Cache data
    std::unordered_map<std::string, std::unique_ptr<Scene>> cached_scenes_by_uid_;
    std::unordered_map<std::string, Scene*> cached_scenes_by_camera_id_;
    std::unordered_map<std::string, Scene*> cached_scenes_by_sensor_id_;
    std::unordered_map<std::string, nlohmann::json> cached_child_transforms_by_uid_;
    std::unordered_map<std::string, nlohmann::json> camera_parameters_;
    
    // Cache metadata
    double cache_refreshed_;
    static constexpr double REFRESH_TIME = 60.0; // seconds
    
    // Helper methods
    void refreshCameras(nlohmann::json& scene_data);
    void updateSceneIndex(Scene* scene);
    void removeSceneFromIndex(const std::string& uid);
};

} // namespace scenescape
