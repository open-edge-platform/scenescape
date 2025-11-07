#include "message_handler.h"
#include "logger.h"
#include "time_chunk_scheduler.h"
#include "metrics_manager.h"
#include "trace_manager.h"
#include <chrono>
#include <quill/LogMacros.h>
#include <shared_mutex>

#include <opentelemetry/trace/scope.h>
#include <opentelemetry/trace/span.h>
#include <opentelemetry/trace/span_startoptions.h>

MessageHandler::MessageHandler(Publisher& publisher, const SceneConfiguration& scene_config,
                               int time_chunking_fps, double max_lag_seconds)
    : publisher_(publisher), time_chunking_fps_(time_chunking_fps),
      max_lag_seconds_(max_lag_seconds) {
    // Calculate time chunking interval from FPS
    int interval_ms = 1000 / time_chunking_fps;

    LOG_INFO(logger::get_logger(), "Time chunking enabled: {} FPS ({}ms interval), max lag: {}s",
             time_chunking_fps, interval_ms, max_lag_seconds);

    // Build camera-to-scene and scene-to-name mappings from scene_config
    // Store camera configs for lazy tracker initialization per category
    for (const auto& scene : scene_config.scenes) {
        scene_to_name_[scene.id] = scene.name;

        // Collect cameras for this scene
        std::vector<CameraConfig> scene_cameras;
        for (const auto& camera_id : scene.camera_ids) {
            camera_to_scene_[camera_id] = scene.id;

            // Find camera config
            auto cam_it =
                std::find_if(scene_config.cameras.begin(), scene_config.cameras.end(),
                             [&camera_id](const CameraConfig& c) { return c.id == camera_id; });
            if (cam_it != scene_config.cameras.end()) {
                scene_cameras.push_back(*cam_it);
            }
        }

        // Store camera configs for lazy initialization
        if (!scene_cameras.empty()) {
            scene_cameras_[scene.id] = std::move(scene_cameras);
            LOG_INFO(logger::get_logger(),
                     "Registered scene '{}' with {} cameras (trackers will be created per-category "
                     "on demand)",
                     scene.name, scene_cameras_[scene.id].size());
        } else {
            LOG_WARNING(logger::get_logger(), "Scene '{}' has no valid cameras", scene.name);
        }
    }

    LOG_INFO(logger::get_logger(), "Built camera-to-scene mapping for {} cameras across {} scenes",
             camera_to_scene_.size(), scene_config.scenes.size());
}

MessageHandler::~MessageHandler() {
    // Unregister all processors from the scheduler and stop workers
    auto& scheduler = TimeChunkScheduler::getInstance();
    {
        std::unique_lock<std::shared_mutex> lock(processors_mutex_);
        for (auto& [scene_id, cat_map] : time_chunk_processors_) {
            for (auto& [category, proc_ptr] : cat_map) {
                if (proc_ptr) {
                    scheduler.unregisterProcessor(proc_ptr.get());
                    proc_ptr->stop();
                }
            }
        }
        time_chunk_processors_.clear();
    }

    // Optionally stop the scheduler when no processors remain
    scheduler.stop();
}

Tracker* MessageHandler::get_or_create_tracker(const std::string& scene_id,
                                               const std::string& category) {
    // First try with shared lock (read)
    {
        std::shared_lock<std::shared_mutex> lock(trackers_mutex_);
        auto scene_it = scene_trackers_.find(scene_id);
        if (scene_it != scene_trackers_.end()) {
            auto category_it = scene_it->second.find(category);
            if (category_it != scene_it->second.end()) {
                return category_it->second.get();
            }
        }
    }

    // Not found, acquire exclusive lock to create
    std::unique_lock<std::shared_mutex> lock(trackers_mutex_);

    // Double-check after acquiring exclusive lock (another thread may have created it)
    auto& category_map = scene_trackers_[scene_id];
    auto category_it = category_map.find(category);
    if (category_it != category_map.end()) {
        return category_it->second.get();
    }

    // Get camera configs for this scene
    auto cameras_it = scene_cameras_.find(scene_id);
    if (cameras_it == scene_cameras_.end()) {
        LOG_ERROR(logger::get_logger(), "No camera configs found for scene {}", scene_id);
        return nullptr;
    }

    // Create new tracker for this scene+category
    auto tracker = std::make_unique<Tracker>(cameras_it->second);
    auto* tracker_ptr = tracker.get();
    category_map[category] = std::move(tracker);

    LOG_INFO(logger::get_logger(), "Created tracker for scene '{}', category '{}' with {} cameras",
             scene_id, category, cameras_it->second.size());

    return tracker_ptr;
}

TimeChunkProcessor* MessageHandler::get_or_create_processor(const std::string& scene_id,
                                                            const std::string& category) {
    // First try with shared lock (read)
    {
        std::shared_lock<std::shared_mutex> lock(processors_mutex_);
        auto scene_it = time_chunk_processors_.find(scene_id);
        if (scene_it != time_chunk_processors_.end()) {
            auto category_it = scene_it->second.find(category);
            if (category_it != scene_it->second.end()) {
                return category_it->second.get();
            }
        }
    }

    // Not found, acquire exclusive lock to create
    std::unique_lock<std::shared_mutex> lock(processors_mutex_);

    // Double-check after acquiring exclusive lock
    auto& category_map = time_chunk_processors_[scene_id];
    auto category_it = category_map.find(category);
    if (category_it != category_map.end()) {
        return category_it->second.get();
    }

    // Get the tracker for this scene+category
    auto* tracker = get_or_create_tracker(scene_id, category);
    if (!tracker) {
        LOG_ERROR(logger::get_logger(), "Failed to get tracker for scene {}, category {}", scene_id,
                  category);
        return nullptr;
    }

    // Get scene name for publishing
    std::string scene_name;
    {
        std::shared_lock<std::shared_mutex> rlock(routing_mutex_);
        auto name_it = scene_to_name_.find(scene_id);
        if (name_it != scene_to_name_.end()) {
            scene_name = name_it->second;
        }
    }

    // Create time chunk processor with category-aware publishing callback
    int interval_ms = 1000 / time_chunking_fps_;
    auto callback = [this, scene_id, scene_name,
                     category](const std::string& camera_id,
                               const std::vector<rv::tracking::TrackedObject>& tracks,
                               std::chrono::system_clock::time_point timestamp) {
        // Publish tracks with actual category
        if (!tracks.empty()) {
            std::string publish_topic = "scenescape/data/scene/" + scene_id + "/" + category;

            try {
                publisher_.publish(publish_topic, scene_id, scene_name, camera_id, tracks,
                                   timestamp);
            } catch (const std::exception& e) {
                LOG_ERROR(logger::get_logger(), "Error publishing tracks: {}", e.what());
            }
        }
    };

    auto processor = std::make_unique<TimeChunkProcessor>(tracker, scene_id, interval_ms, callback);
    // Start worker thread; scheduler will drive ticks
    processor->start();

    // Register with global scheduler (single-interval loop)
    auto& scheduler = TimeChunkScheduler::getInstance();
    scheduler.configure(std::chrono::milliseconds(interval_ms));
    scheduler.start();

    auto* processor_ptr = processor.get();
    scheduler.registerProcessor(processor_ptr);
    category_map[category] = std::move(processor);

    LOG_INFO(logger::get_logger(), "Created TimeChunkProcessor for scene '{}', category '{}'",
             scene_id, category);

    return processor_ptr;
}

void MessageHandler::handleDetectionMessage(const CameraDetectionMsg& detectionMsg) {
    auto& metricsManager = MetricsManager::getInstance();

    // Time the entire MQTT handler duration (validation + buffering)
    auto mqtt_start = std::chrono::steady_clock::now();

    // Increment message counter
    metricsManager.incrementMqttMessagesReceived();

    // Validate timestamp - check for fell_behind condition
    auto now = std::chrono::system_clock::now();
    auto msg_timestamp = detectionMsg.get_timestamp();
    auto lag = std::chrono::duration<double>(std::abs(
        std::chrono::duration_cast<std::chrono::duration<double>>(now - msg_timestamp).count()));

    if (lag.count() > max_lag_seconds_) {
        LOG_WARNING(logger::get_logger(),
                    "scenescape/data/camera/{} FELL BEHIND by {:.2f}s. SKIPPING {}",
                    detectionMsg.id, lag.count(), detectionMsg.id);
        metricsManager.incrementDropped("fell_behind");
        return;
    }

    // Determine scene ID from camera ID (with shared lock)
    const std::string& camera_id = detectionMsg.id;
    std::string scene_id;
    {
        std::shared_lock<std::shared_mutex> lock(routing_mutex_);
        auto scene_it = camera_to_scene_.find(camera_id);
        if (scene_it == camera_to_scene_.end()) {
            LOG_WARNING(logger::get_logger(), "Camera {} not associated with any scene, skipping",
                        camera_id);
            return;
        }
        scene_id = scene_it->second;
    }

    // Extract category from detection message (group by category)
    // Collect detections per category
    std::unordered_map<std::string, std::vector<Person>> detections_by_category;
    for (const auto& person : detectionMsg.persons) {
        if (!person.category.empty()) {
            detections_by_category[person.category].push_back(person);
        } else {
            // Skip detections with missing category
            LOG_WARNING(logger::get_logger(),
                        "Detection from camera {} has empty category field, skipping object",
                        camera_id);
            metricsManager.incrementDropped("missing_category");
        }
    }

    // Process each category separately
    for (const auto& [category, persons] : detections_by_category) {
        // Get or create time chunk processor for this scene+category
        TimeChunkProcessor* processor = get_or_create_processor(scene_id, category);
        if (!processor) {
            LOG_WARNING(logger::get_logger(),
                        "Failed to get/create processor for scene {}, category {}, skipping",
                        scene_id, category);
            continue;
        }

        // Create a filtered detection message with only this category's persons
        CameraDetectionMsg filtered_msg = detectionMsg;
        filtered_msg.persons = persons;

        // Add detection to time chunk buffer
        processor->add_detection(filtered_msg);
    }

    // Record MQTT handler duration (validation + buffering only)
    auto mqtt_end = std::chrono::steady_clock::now();
    auto mqtt_duration_ms =
        std::chrono::duration_cast<std::chrono::nanoseconds>(mqtt_end - mqtt_start).count() / 1e6;
    metricsManager.recordMqttHandlerDuration(mqtt_duration_ms, detectionMsg.id);
}
