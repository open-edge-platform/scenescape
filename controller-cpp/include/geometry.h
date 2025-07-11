#pragma once

#include <vector>
#include <string>
#include <nlohmann/json.hpp>

namespace scenescape {

struct Point {
    double x, y, z;
    
    Point(double x = 0, double y = 0, double z = 0) : x(x), y(y), z(z) {}
    
    Point operator+(const Point& other) const {
        return Point(x + other.x, y + other.y, z + other.z);
    }
    
    Point operator-(const Point& other) const {
        return Point(x - other.x, y - other.y, z - other.z);
    }
    
    Point operator*(double scalar) const {
        return Point(x * scalar, y * scalar, z * scalar);
    }
    
    double distance(const Point& other) const;
    double length() const;
    Point normalize() const;
    
    nlohmann::json toJson() const;
    static Point fromJson(const nlohmann::json& json);
};

struct Region {
    std::string id;
    std::string name;
    std::vector<Point> points;
    std::string region_type; // "roi", "hazard_zone", etc.
    
    bool contains(const Point& point) const;
    double area() const;
    Point centroid() const;
    
    nlohmann::json toJson() const;
    static Region fromJson(const nlohmann::json& json);
};

struct Tripwire {
    std::string id;
    std::string name;
    Point start;
    Point end;
    double debounce_time;
    
    // Check if a point crossed the tripwire
    // Returns: -1 (left), 0 (no crossing), 1 (right)
    int checkCrossing(const Point& previous, const Point& current) const;
    
    nlohmann::json toJson() const;
    static Tripwire fromJson(const nlohmann::json& json);
};

struct Camera {
    std::string id;
    std::string name;
    Point position;
    Point rotation; // Euler angles
    
    // Camera intrinsics
    struct Intrinsics {
        double fx, fy, cx, cy;
        Intrinsics(double fx = 0, double fy = 0, double cx = 0, double cy = 0)
            : fx(fx), fy(fy), cx(cx), cy(cy) {}
    } intrinsics;
    
    // Distortion coefficients
    struct Distortion {
        double k1, k2, p1, p2, k3;
        Distortion(double k1 = 0, double k2 = 0, double p1 = 0, double p2 = 0, double k3 = 0)
            : k1(k1), k2(k2), p1(p1), p2(p2), k3(k3) {}
    } distortion;
    
    // Transform point from camera coordinates to scene coordinates
    Point cameraToScene(const Point& camera_point) const;
    Point sceneToCamera(const Point& scene_point) const;
    
    // Check if a point is visible from this camera
    bool isVisible(const Point& scene_point) const;
    
    nlohmann::json toJson() const;
    static Camera fromJson(const nlohmann::json& json);
};

struct Sensor {
    std::string id;
    std::string name;
    Point position;
    std::string sensor_type;
    nlohmann::json metadata;
    
    nlohmann::json toJson() const;
    static Sensor fromJson(const nlohmann::json& json);
};

// Utility functions for geometric calculations
double pointToLineDistance(const Point& point, const Point& line_start, const Point& line_end);
bool pointInPolygon(const Point& point, const std::vector<Point>& polygon);
double polygonArea(const std::vector<Point>& polygon);

} // namespace scenescape
