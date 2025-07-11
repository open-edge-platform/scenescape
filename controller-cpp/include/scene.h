#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <nlohmann/json.hpp>
#include "moving_object.h"
#include "geometry.h"

namespace scenescape {

class Scene {
public:
    Scene(
        const std::string& name, 
        const std::string& map_file, 
        double scale = 1.0,
        double max_unreliable_time = 3.0,
        double non_measurement_time_dynamic = 1.0,
        double non_measurement_time_static = 3.0
    );
    
    ~Scene() = default;

    // Static factory method
    static std::unique_ptr<Scene> deserialize(const nlohmann::json& scene_data);
    
    // Update methods
    void updateScene(const nlohmann::json& scene_data);
    void updateCameras(const nlohmann::json& cameras_data);
    void updateRegions(const nlohmann::json& regions_data);
    void updateTripwires(const nlohmann::json& tripwires_data);
    
    // Object tracking
    void processDetections(
        const std::string& camera_id,
        const std::vector<nlohmann::json>& detections,
        double timestamp,
        const std::string& object_type
    );
    
    std::vector<MovingObject> getTrackedObjects(const std::string& object_type) const;
    
    // Getters
    const std::string& getName() const { return name_; }
    const std::string& getUID() const { return uid_; }
    const std::unordered_map<std::string, Camera>& getCameras() const { return cameras_; }
    const std::unordered_map<std::string, Region>& getRegions() const { return regions_; }
    const std::unordered_map<std::string, Tripwire>& getTripwires() const { return tripwires_; }
    
    // Visibility checking
    bool isVisible(const Point& point, const std::string& camera_id) const;
    std::vector<std::string> getVisibleCameras(const Point& point) const;
    
    // Event handling
    struct TripwireEvent {
        MovingObject object;
        int direction;
    };
    
    std::vector<TripwireEvent> checkTripwireEvents(
        const std::vector<MovingObject>& objects
    );
    
    // Publication tracking
    std::unordered_map<std::string, int> last_pub_count;
    std::unordered_map<std::string, std::optional<double>> last_published_detection;

private:
    // Basic properties
    std::string name_;
    std::string uid_;
    std::string map_file_;
    double scale_;
    
    // Timing parameters
    double max_unreliable_time_;
    double non_measurement_time_dynamic_;
    double non_measurement_time_static_;
    
    // Scene components
    std::unordered_map<std::string, Camera> cameras_;
    std::unordered_map<std::string, Region> regions_;
    std::unordered_map<std::string, Tripwire> tripwires_;
    std::unordered_map<std::string, Sensor> sensors_;
    
    // Tracking state
    std::unordered_map<std::string, std::vector<MovingObject>> tracked_objects_;
    std::unique_ptr<class Tracker> tracker_;
    
    // Reference frame rate
    std::optional<double> ref_camera_frame_rate_;
    
    // Helper methods
    void initializeTracker();
    void loadMapFile(const std::string& map_file);
    Point transformCameraToScene(const Point& camera_point, const std::string& camera_id) const;
    std::vector<Point> computeCameraBounds(const std::string& camera_id) const;
};

} // namespace scenescape
