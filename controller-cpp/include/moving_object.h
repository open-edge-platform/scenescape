#pragma once

#include <string>
#include <vector>
#include <optional>
#include <nlohmann/json.hpp>
#include "geometry.h"

namespace scenescape {

class MovingObject {
public:
    MovingObject(
        const std::string& id,
        const std::string& category,
        const Point& position,
        double timestamp,
        double confidence = 1.0
    );
    
    ~MovingObject() = default;

    // Getters
    const std::string& getId() const { return id_; }
    const std::string& getCategory() const { return category_; }
    const Point& getPosition() const { return position_; }
    const Point& getVelocity() const { return velocity_; }
    double getTimestamp() const { return timestamp_; }
    double getConfidence() const { return confidence_; }
    
    // State properties
    bool isReliable() const { return reliable_; }
    bool isVisible() const { return visible_; }
    bool isDynamic() const { return dynamic_; }
    
    // Update methods
    void updatePosition(const Point& position, double timestamp);
    void updateVelocity(const Point& velocity);
    void setReliable(bool reliable) { reliable_ = reliable; }
    void setVisible(bool visible) { visible_ = visible; }
    void setDynamic(bool dynamic) { dynamic_ = dynamic; }
    void setConfidence(double confidence) { confidence_ = confidence; }
    
    // Tracking properties
    void addMeasurement(const Point& position, double timestamp);
    void predict(double timestamp);
    bool hasRecentMeasurement(double current_time, double max_age) const;
    
    // Serialization
    nlohmann::json toJson() const;
    static MovingObject fromJson(const nlohmann::json& json);
    
    // Bounding box
    struct BoundingBox {
        double x, y, width, height;
        
        BoundingBox(double x = 0, double y = 0, double w = 0, double h = 0)
            : x(x), y(y), width(w), height(h) {}
        
        Point center() const { return Point(x + width/2, y + height/2); }
        double area() const { return width * height; }
    };
    
    void setBoundingBox(const BoundingBox& bbox) { bounding_box_ = bbox; }
    const std::optional<BoundingBox>& getBoundingBox() const { return bounding_box_; }

private:
    // Identity
    std::string id_;
    std::string category_;
    
    // Spatial properties
    Point position_;
    Point velocity_;
    std::optional<BoundingBox> bounding_box_;
    
    // Temporal properties
    double timestamp_;
    double last_measurement_time_;
    
    // State flags
    bool reliable_;
    bool visible_;
    bool dynamic_;
    double confidence_;
    
    // History for tracking
    std::vector<std::pair<Point, double>> position_history_;
    static constexpr size_t MAX_HISTORY_SIZE = 10;
    
    // Helper methods
    void updateVelocityFromHistory();
    void trimHistory();
};

} // namespace scenescape
