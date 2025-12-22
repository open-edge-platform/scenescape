#pragma once

#include "config.h"
#include "mqtt_msg.h"
#include "config/scene_config.h"
#include "rv/tracking/TrackTracker.hpp"
#include <vector>

class Tracker {
public:
    // Construct tracker with camera calibration configs
    Tracker(const std::vector<CameraConfig>& cameras);
    ~Tracker();

    // Disable copy
    Tracker(const Tracker&) = delete;
    Tracker& operator=(const Tracker&) = delete;

    // Process incoming detection message
    /*
    std::vector<rv::tracking::TrackedObject> process_detections(const CameraDetectionMsg& msg);
    */
    // Process a batch of detections (one time chunk across multiple cameras)
    // Returns reliable tracks after applying all detections in the batch
    std::vector<rv::tracking::TrackedObject>
    process_detections_batch(const std::vector<CameraDetectionMsg>& msgs);

    // Check if tracker is currently processing (for back-pressure detection)
    bool is_busy() const;

private:
    class Impl;
    std::unique_ptr<Impl> pImpl_;
};
