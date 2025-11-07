#include "tracker.h"
#include "config.h"
#include "entities.h"
#include "logger.h"
#include "metrics_manager.h"
#include "rv/tracking/CameraUtils.hpp"
#include "rv/tracking/TrackedObject.hpp"
#include "rv/tracking/TrackTracker.hpp"
#include "trace_manager.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <opencv2/core.hpp>
#include <quill/LogMacros.h>
#include <stdexcept>
#include <unordered_map>

#include <opentelemetry/trace/span.h>

const cv::Mat dummy_intrinsics = (cv::Mat_<double>(3, 3) << 1000.0, 0.0, 640.0, // fx, 0, cx
                                  0.0, 1000.0, 480.0,                           // 0, fy, cy
                                  0.0, 0.0, 1.0);                               // 0, 0, 1
const cv::Mat dummy_distortion = (cv::Mat_<double>(5, 1) << 0.0, 0.0, 0.0, 0.0, 0.0);

namespace {
void print_track(const rv::tracking::TrackedObject& track) {
    LOG_TRACE_L3(logger::get_logger(),
                 "  Track ID: {}, Position: ({:.4f}, {:.4f}, {:.4f}), Velocity: ({:.4f}, {:.4f}), "
                 "Size: ({:.4f} x {:.4f} x {:.4f})",
                 track.id, track.x, track.y, track.z, track.vx, track.vy, track.length, track.width,
                 track.height);
}
} // namespace

class Tracker::Impl {
public:
    Impl(const std::vector<CameraConfig>& cameras) : is_processing_(false) {
        if (cameras.empty()) {
            throw std::runtime_error(
                "No cameras configured. Tracker requires camera intrinsics/distortion.");
        }
        // Build map of camera id -> rv::CameraParams
        for (const auto& cam : cameras) {
            // Persist per-camera calibration matrices to ensure stable lifetime
            cv::Mat intrinsics =
                (cv::Mat_<double>(3, 3) << cam.intrinsics.fx, 0.0, cam.intrinsics.cx, 0.0,
                 cam.intrinsics.fy, cam.intrinsics.cy, 0.0, 0.0, 1.0);
            cv::Mat distortion = (cv::Mat_<double>(5, 1) << cam.distortion.k1, cam.distortion.k2,
                                  cam.distortion.p1, cam.distortion.p2, 0.0);

            // Store clones so data buffers are owned by this object
            intrinsics_by_id_.emplace(cam.id, intrinsics.clone());
            distortions_by_id_.emplace(cam.id, distortion.clone());

            camera_params_.emplace(cam.id, rv::CameraParams{intrinsics_by_id_.at(cam.id),
                                                            distortions_by_id_.at(cam.id)});
        }
    }
/*
    std::vector<rv::tracking::TrackedObject> process_detections(const CameraDetectionMsg& msg) {
        // Set busy flag for back-pressure detection
        is_processing_.store(true, std::memory_order_release);
        auto& traceManager = TraceManager::getInstance();

        // Select camera parameters based on detection message camera id
        rv::CameraParams cam_params = getCameraParams(msg.id);
        LOG_DEBUG(logger::get_logger(),
                  "Processing detection message from camera id '{}', {} persons detected", msg.id,
                  msg.persons.size());

        // Child span: Coordinate transformation
        opentelemetry::nostd::shared_ptr<opentelemetry::trace::Span> transform_span;
        if (traceManager.isEnabled()) {
            auto tracer = traceManager.getTracer();
            transform_span = tracer->StartSpan("transform_pixel_to_world");
            transform_span->SetAttribute("objects.count", static_cast<int64_t>(msg.persons.size()));
        }

        auto transform_start = std::chrono::steady_clock::now();

        // Process each detected person in parallel using OpenMP
        std::vector<rv::tracking::TrackedObject> tracked_objects(msg.persons.size());
        // #pragma omp parallel for
        for (size_t i = 0; i < msg.persons.size(); ++i) {
            const auto& person = msg.persons[i];

            // Convert bounding box from pixels to world coordinates (undistorted)
            auto world_coords = rv::computePixelsToMeterPlane(
                cv::Rect2f(person.bounding_box_px.x, person.bounding_box_px.y,
                           person.bounding_box_px.width, person.bounding_box_px.height),
                cam_params);

            // Create a tracked object from the detection
            rv::tracking::TrackedObject& to = tracked_objects[i];
            to.id = person.id; // Preserve the detection ID for tracking
            to.x = world_coords.x + world_coords.width / 2.0;
            to.y = world_coords.y + world_coords.height / 2.0;
            to.z = 0.0; // Assuming ground plane
            to.length = world_coords.width;
            to.width = world_coords.width;
            to.height = world_coords.height;
        }

        auto transform_end = std::chrono::steady_clock::now();
        auto transform_duration_ms =
            std::chrono::duration_cast<std::chrono::nanoseconds>(transform_end - transform_start)
                .count() /
            1e6;

        if (transform_span) {
            transform_span->SetAttribute("duration_ms", transform_duration_ms);
            transform_span->End();
        }

        // Child span: Tracker update
        opentelemetry::nostd::shared_ptr<opentelemetry::trace::Span> tracker_span;
        if (traceManager.isEnabled()) {
            auto tracer = traceManager.getTracer();
            tracker_span = tracer->StartSpan("tracker_update");
            tracker_span->SetAttribute("detections.input",
                                       static_cast<int64_t>(tracked_objects.size()));
        }

        auto tracker_start = std::chrono::steady_clock::now();

        // Process the tracked objects with the persistent tracker instance
        track_tracker_.track(tracked_objects, msg.get_timestamp());

        // Print all active tracks
        auto all_tracks = track_tracker_.getTracks();
        LOG_TRACE_L3(logger::get_logger(), "=== All Active Tracks ===");
        for (const auto& track : all_tracks) {
            print_track(track);
        }

        // Print reliable tracks
        auto reliable_tracks = track_tracker_.getReliableTracks();
        LOG_TRACE_L3(logger::get_logger(), "=== Reliable Tracks ===");
        for (const auto& track : reliable_tracks) {
            print_track(track);
        }

        auto tracker_end = std::chrono::steady_clock::now();
        auto tracker_duration_ms =
            std::chrono::duration_cast<std::chrono::nanoseconds>(tracker_end - tracker_start)
                .count() /
            1e6;

        if (tracker_span) {
            tracker_span->SetAttribute("tracks.output",
                                       static_cast<int64_t>(reliable_tracks.size()));
            tracker_span->SetAttribute("tracks.all", static_cast<int64_t>(all_tracks.size()));
            tracker_span->SetAttribute("duration_ms", tracker_duration_ms);
            tracker_span->End();
        }

        // Record active tracks metrics
        MetricsManager::getInstance().recordActiveTracks(
            static_cast<int64_t>(reliable_tracks.size()),
            static_cast<int64_t>(all_tracks.size()));

        // Clear busy flag
        is_processing_.store(false, std::memory_order_release);

        return reliable_tracks;
    }
*/
    std::vector<rv::tracking::TrackedObject>
    process_detections_batch(const std::vector<CameraDetectionMsg>& msgs) {
        // Set busy flag for back-pressure detection
        is_processing_.store(true, std::memory_order_release);
        auto& traceManager = TraceManager::getInstance();

        // Parent span for batch processing
        opentelemetry::nostd::shared_ptr<opentelemetry::trace::Span> batch_span;
        if (traceManager.isEnabled()) {
            auto tracer = traceManager.getTracer();
            batch_span = tracer->StartSpan("process_scene_chunk_batch");
            batch_span->SetAttribute("detections.cameras", static_cast<int64_t>(msgs.size()));
        }

        auto batch_start = std::chrono::steady_clock::now();

        // For each camera message, transform and feed into the tracker sequentially
        for (const auto& msg : msgs) {
            // Select camera parameters based on detection message camera id
            rv::CameraParams cam_params = getCameraParams(msg.id);

            // Transform detections for this camera
            std::vector<rv::tracking::TrackedObject> tracked_objects(msg.persons.size());
            for (size_t i = 0; i < msg.persons.size(); ++i) {
                const auto& person = msg.persons[i];
                auto world_coords = rv::computePixelsToMeterPlane(
                    cv::Rect2f(person.bounding_box_px.x, person.bounding_box_px.y,
                               person.bounding_box_px.width, person.bounding_box_px.height),
                    cam_params);

                rv::tracking::TrackedObject& to = tracked_objects[i];
                to.id = person.id;
                to.x = world_coords.x + world_coords.width / 2.0;
                to.y = world_coords.y + world_coords.height / 2.0;
                to.z = 0.0;
                to.length = world_coords.width;
                to.width = world_coords.width;
                to.height = world_coords.height;
            }

            // Feed detections for this camera with its timestamp
            track_tracker_.track(tracked_objects, msg.get_timestamp());
        }

        // After applying all cameras in the chunk, observe final tracker state
        auto all_tracks = track_tracker_.getTracks();
        auto reliable_tracks = track_tracker_.getReliableTracks();

        auto batch_end = std::chrono::steady_clock::now();
        auto batch_duration_ms =
            std::chrono::duration_cast<std::chrono::nanoseconds>(batch_end - batch_start).count() /
            1e6;

        if (batch_span) {
            batch_span->SetAttribute("tracks.output", static_cast<int64_t>(reliable_tracks.size()));
            batch_span->SetAttribute("tracks.all", static_cast<int64_t>(all_tracks.size()));
            batch_span->SetAttribute("duration_ms", batch_duration_ms);
            batch_span->End();
        }

        // Record active tracks metrics once per batch
        MetricsManager::getInstance().recordActiveTracks(
            static_cast<int64_t>(reliable_tracks.size()), static_cast<int64_t>(all_tracks.size()));

        // Clear busy flag
        is_processing_.store(false, std::memory_order_release);

        return reliable_tracks;
    }

    bool is_busy() const { return is_processing_.load(std::memory_order_acquire); }

private:
    rv::tracking::TrackTracker track_tracker_;
    std::unordered_map<std::string, rv::CameraParams> camera_params_;
    std::unordered_map<std::string, cv::Mat> intrinsics_by_id_;
    std::unordered_map<std::string, cv::Mat> distortions_by_id_;
    std::atomic<bool> is_processing_;

    rv::CameraParams getCameraParams(const std::string& camera_id) const {
        auto it = camera_params_.find(camera_id);
        if (it != camera_params_.end()) {
            return it->second;
        }
        LOG_ERROR(logger::get_logger(),
                  "Camera id '{}' not found in configuration. Aborting processing.", camera_id);
        throw std::runtime_error("Camera configuration missing for id: " + camera_id);
    }
};

Tracker::Tracker(const std::vector<CameraConfig>& cameras)
    : pImpl_(std::make_unique<Impl>(cameras)) {}

Tracker::~Tracker() = default;

/*
std::vector<rv::tracking::TrackedObject>
Tracker::process_detections(const CameraDetectionMsg& msg) {
    return pImpl_->process_detections(msg);
}*/

bool Tracker::is_busy() const {
    return pImpl_->is_busy();
}

std::vector<rv::tracking::TrackedObject>
Tracker::process_detections_batch(const std::vector<CameraDetectionMsg>& msgs) {
    return pImpl_->process_detections_batch(msgs);
}
