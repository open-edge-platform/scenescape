#include "scene_controller.h"
#include "timestamp.h"
#include "detections_builder.h"
#include <fstream>
#include <chrono>
#include <iostream>

namespace scenescape {

constexpr int AVG_FRAMES = 100;

SceneController::SceneController(
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
) : rewrite_bad_time_(rewrite_bad_time),
    rewrite_all_time_(rewrite_all_time),
    max_lag_(max_lag),
    broker_(mqtt_broker),
    mqtt_auth_(mqtt_auth),
    ntp_server_(ntp_server),
    visibility_topic_(visibility_topic),
    time_offset_(0.0) {
    
    // Extract tracker configuration
    if (!tracker_config_file.empty()) {
        extractTrackerConfigData(tracker_config_file);
    }
    
    // Initialize MQTT client
    mqtt_client_ = std::make_unique<MqttClient>(
        mqtt_broker, mqtt_auth, client_cert, root_cert
    );
    
    mqtt_client_->setOnConnectCallback([this]() { onConnect(); });
    mqtt_client_->setOnMessageCallback([this](const std::string& topic, const std::string& payload) {
        onMessage(topic, payload);
    });
    
    // Initialize cache manager
    cache_manager_ = std::make_unique<CacheManager>(
        rest_url, rest_auth, root_cert, tracker_config_data_
    );
    
    std::cout << "Publishing camera visibility info on " << visibility_topic_ << " topic.\n";
}

SceneController::~SceneController() = default;

void SceneController::loopForever() {
    mqtt_client_->connect();
    mqtt_client_->loopForever();
}

void SceneController::extractTrackerConfigData(const std::string& tracker_config_file) {
    std::ifstream file(tracker_config_file);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open tracker config file: " + tracker_config_file);
    }
    
    nlohmann::json config;
    file >> config;
    
    if (config.contains("max_unreliable_frames") && 
        config.contains("baseline_frame_rate") &&
        config.contains("non_measurement_frames_dynamic") &&
        config.contains("non_measurement_frames_static")) {
        
        double baseline_frame_rate = config["baseline_frame_rate"];
        tracker_config_data_["max_unreliable_time"] = 
            config["max_unreliable_frames"].get<double>() / baseline_frame_rate;
        tracker_config_data_["non_measurement_time_dynamic"] = 
            config["non_measurement_frames_dynamic"].get<double>() / baseline_frame_rate;
        tracker_config_data_["non_measurement_time_static"] = 
            config["non_measurement_frames_static"].get<double>() / baseline_frame_rate;
    }
}

void SceneController::onConnect() {
    std::cout << "Connected to MQTT broker\n";
    
    // Subscribe to relevant topics
    mqtt_client_->subscribe("scenescape/data/camera/+");
    mqtt_client_->subscribe("scenescape/external/+/+");
    mqtt_client_->subscribe("scenescape/data/sensor/+");
    mqtt_client_->subscribe("scenescape/cmd/scene/update/+");
    
    // Refresh scenes from cache
    cache_manager_->refreshScenes();
}

void SceneController::onMessage(const std::string& topic, const std::string& payload) {
    try {
        nlohmann::json jdata = nlohmann::json::parse(payload);
        
        // Handle different message types based on topic
        if (topic.find("/data/camera/") != std::string::npos) {
            // Extract camera ID from topic
            size_t pos = topic.find("/data/camera/");
            std::string camera_id = topic.substr(pos + 13);
            
            // Find scene for this camera
            Scene* scene = cache_manager_->getSceneByCameraID(camera_id);
            if (!scene) {
                std::cerr << "No scene found for camera: " << camera_id << std::endl;
                return;
            }
            
            // Process camera detections
            if (jdata.contains("objects") && jdata.contains("timestamp")) {
                double timestamp = getEpochTime(jdata["timestamp"].get<std::string>());
                timestamp = adjustTime(timestamp);
                
                for (const auto& [object_type, detections] : jdata["objects"].items()) {
                    if (detections.is_array() && !detections.empty()) {
                        scene->processDetections(camera_id, detections, timestamp, object_type);
                        
                        // Get tracked objects and publish
                        auto tracked_objects = scene->getTrackedObjects(object_type);
                        publishDetections(scene, tracked_objects, timestamp, object_type, jdata, camera_id);
                    }
                }
            }
        }
        else if (topic.find("/external/") != std::string::npos) {
            // Handle external sensor data
            // Extract scene ID and object type from topic
            size_t pos1 = topic.find("/external/");
            size_t pos2 = topic.find("/", pos1 + 10);
            if (pos2 != std::string::npos) {
                std::string scene_id = topic.substr(pos1 + 10, pos2 - pos1 - 10);
                std::string object_type = topic.substr(pos2 + 1);
                
                Scene* scene = cache_manager_->getSceneByUID(scene_id);
                if (scene && jdata.contains("timestamp")) {
                    double timestamp = getEpochTime(jdata["timestamp"].get<std::string>());
                    timestamp = adjustTime(timestamp);
                    
                    // Process external detection
                    std::vector<nlohmann::json> detections = {jdata};
                    scene->processDetections("external", detections, timestamp, object_type);
                    
                    auto tracked_objects = scene->getTrackedObjects(object_type);
                    publishDetections(scene, tracked_objects, timestamp, object_type, jdata, "external");
                }
            }
        }
        else if (topic.find("/cmd/scene/update/") != std::string::npos) {
            // Scene update command - refresh cache
            cache_manager_->refreshScenes();
        }
        
    } catch (const std::exception& e) {
        std::cerr << "Error processing message: " << e.what() << std::endl;
    }
}

void SceneController::publishDetections(
    Scene* scene, 
    const std::vector<MovingObject>& objects, 
    double timestamp, 
    const std::string& object_type, 
    const nlohmann::json& jdata, 
    const std::string& camera_id
) {
    publishSceneDetections(scene, objects, object_type, jdata);
    publishRegulatedDetections(scene, objects, object_type, jdata, camera_id);
    publishRegionDetections(scene, objects, object_type, jdata);
}

void SceneController::publishSceneDetections(
    Scene* scene, 
    const std::vector<MovingObject>& objects, 
    const std::string& object_type, 
    const nlohmann::json& jdata
) {
    // Build detections list
    nlohmann::json pub_data = jdata;
    pub_data["objects"] = buildDetectionsList(objects, scene, visibility_topic_ == "unregulated");
    
    int object_count = pub_data["objects"].size();
    std::string cache_id = scene->getName() + "/" + object_type;
    
    // Check if we should publish (has objects or last publish had objects)
    if (object_count > 0 || 
        (scene->last_pub_count.count(cache_id) && scene->last_pub_count[cache_id] > 0)) {
        
        // Add processing time if available
        if (jdata.contains("debug_hmo_start_time")) {
            pub_data["debug_hmo_processing_time"] = getEpochTime() - jdata["debug_hmo_start_time"].get<double>();
        }
        
        std::string topic = "scenescape/data/scene/" + scene->getUID() + "/" + object_type;
        mqtt_client_->publish(topic, pub_data.dump());
        
        scene->last_pub_count[cache_id] = object_count;
    }
}

void SceneController::publishRegulatedDetections(
    Scene* scene, 
    const std::vector<MovingObject>& objects, 
    const std::string& object_type, 
    const nlohmann::json& jdata, 
    const std::string& camera_id
) {
    if (visibility_topic_ != "regulated") {
        return;
    }
    
    double now = getEpochTime();
    double max_delay = 1.0; // 1 second max delay for regulated publishing
    
    std::string regulate_key = scene->getName() + "/" + camera_id + "/" + object_type;
    
    if (shouldPublish(
        regulate_cache_[scene->getName()].count(regulate_key) ? 
            std::optional<double>(regulate_cache_[scene->getName()][regulate_key]) : 
            std::nullopt, 
        now, max_delay)) {
        
        nlohmann::json regulated_data = jdata;
        regulated_data["objects"] = buildDetectionsList(objects, scene, true);
        
        std::string topic = "scenescape/regulated/scene/" + scene->getUID();
        mqtt_client_->publish(topic, regulated_data.dump());
        
        regulate_cache_[scene->getName()][regulate_key] = now;
    }
}

void SceneController::publishRegionDetections(
    Scene* scene, 
    const std::vector<MovingObject>& objects, 
    const std::string& object_type, 
    const nlohmann::json& jdata
) {
    // Check for region events and tripwire crossings
    auto tripwire_events = scene->checkTripwireEvents(objects);
    
    for (const auto& event : tripwire_events) {
        nlohmann::json event_data;
        event_data["timestamp"] = getIsoTime();
        event_data["objects"] = nlohmann::json::array({event.object.toJson()});
        event_data["direction"] = event.direction;
        
        std::string topic = "scenescape/event/tripwire/" + scene->getUID() + "/tripwire/" + object_type;
        mqtt_client_->publish(topic, event_data.dump());
    }
    
    // Check region occupancy
    for (const auto& [region_id, region] : scene->getRegions()) {
        int count = 0;
        for (const auto& obj : objects) {
            if (region.contains(obj.getPosition())) {
                count++;
            }
        }
        
        if (count > 0) {
            nlohmann::json region_data = jdata;
            region_data["counts"][object_type] = count;
            region_data["metadata"] = region.toJson();
            
            std::string topic = "scenescape/event/region/" + scene->getUID() + "/" + region_id + "/" + object_type;
            mqtt_client_->publish(topic, region_data.dump());
        }
    }
}

bool SceneController::shouldPublish(
    std::optional<double> last_time, 
    double now, 
    double max_delay
) {
    return !last_time.has_value() || (now - last_time.value()) >= max_delay;
}

void SceneController::syncTime() {
    // TODO: Implement NTP time synchronization
    // For now, use system time
    time_offset_ = 0.0;
    last_time_sync_ = std::chrono::steady_clock::now();
}

double SceneController::adjustTime(double timestamp) {
    if (rewrite_all_time_) {
        return getEpochTime();
    }
    
    double adjusted = timestamp + time_offset_;
    double now = getEpochTime();
    
    if (rewrite_bad_time_ && std::abs(adjusted - now) > max_lag_) {
        return now;
    }
    
    return adjusted;
}

} // namespace scenescape
