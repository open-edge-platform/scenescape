#pragma once

#include <string>
#include <memory>
#include <unordered_map>
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include "cache_manager.h"
#include "scene.h"
#include "mqtt_client.h"

namespace scenescape {

class SceneController {
public:
    SceneController(
        bool rewrite_bad_time,
        bool rewrite_all_time, 
        double max_lag,
        const std::string& mqtt_broker,
        const std::string& mqtt_auth,
        const std::string& rest_url,
        const std::string& rest_auth,
        const std::string& client_cert,
        const std::string& root_cert,
        const std::string& ntp_server,
        const std::string& tracker_config_file,
        const std::string& schema_file,
        const std::string& visibility_topic
    );

    ~SceneController();

    void loopForever();

private:
    // Configuration
    bool rewrite_bad_time_;
    bool rewrite_all_time_;
    double max_lag_;
    std::string broker_;
    std::string mqtt_auth_;
    std::string ntp_server_;
    std::string visibility_topic_;
    
    // Time synchronization
    double time_offset_;
    std::chrono::steady_clock::time_point last_time_sync_;
    
    // Tracker configuration
    nlohmann::json tracker_config_data_;
    
    // Components
    std::unique_ptr<MqttClient> mqtt_client_;
    std::unique_ptr<CacheManager> cache_manager_;
    
    // Scene management
    std::unordered_map<std::string, std::unique_ptr<Scene>> scenes_;
    std::unordered_map<std::string, std::unordered_map<std::string, double>> regulate_cache_;
    
    // Methods
    void extractTrackerConfigData(const std::string& tracker_config_file);
    void onConnect();
    void onMessage(const std::string& topic, const std::string& payload);
    
    void publishDetections(
        Scene* scene, 
        const std::vector<MovingObject>& objects, 
        double timestamp, 
        const std::string& object_type, 
        const nlohmann::json& jdata, 
        const std::string& camera_id
    );
    
    void publishSceneDetections(
        Scene* scene, 
        const std::vector<MovingObject>& objects, 
        const std::string& object_type, 
        const nlohmann::json& jdata
    );
    
    void publishRegulatedDetections(
        Scene* scene, 
        const std::vector<MovingObject>& objects, 
        const std::string& object_type, 
        const nlohmann::json& jdata, 
        const std::string& camera_id
    );
    
    void publishRegionDetections(
        Scene* scene, 
        const std::vector<MovingObject>& objects, 
        const std::string& object_type, 
        const nlohmann::json& jdata
    );
    
    bool shouldPublish(
        std::optional<double> last_time, 
        double now, 
        double max_delay
    );
    
    void syncTime();
    double adjustTime(double timestamp);
};

} // namespace scenescape
