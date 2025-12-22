#include "config.h"
#include "config/config_sources.hpp"
#include "logger.h"
#include "config/scene_config.h"
#include "message_handler.h"
#include "metrics_manager.h"
#include "mqtt_client.h"
#include "publisher.h"
#include "trace_manager.h"
#include "tracker.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <filesystem>
#include <iostream>
#include <memory>
#include <mutex>
#include <quill/LogMacros.h>
#include <sstream>
#include <string>
#include <thread>

#include "config/cli.hpp"
#include "config/config_validation.hpp"

// TODO: Paho library seems to not respect no_proxy settings correctly. Need to investigate further.
void disbleProxy() {
    unsetenv("http_proxy");
    unsetenv("https_proxy");
    unsetenv("HTTP_PROXY");
    unsetenv("HTTPS_PROXY");
    unsetenv("no_proxy");
    unsetenv("NO_PROXY");
}

int main(int argc, char* argv[]) {
    try {
        // Configuration is fully parsed and overlays applied via config_args API

        // Disable proxy settings
        disbleProxy();

        Config config;
        try {
            config = config_args::load_config_from_argv(argc, argv);
        } catch (const std::exception &e) {
            std::cerr << "FATAL: Failed to load configuration: " << e.what() << std::endl;
            return 1;
        }

        logger::initialize(config.logging.level);
        LOG_INFO(logger::get_logger(), "Configuration loaded successfully: {}",
                 (std::ostringstream{} << config).str());

        // Create config source based on configuration (file or API)
        std::unique_ptr<config::IConfigSource> config_source;
        try {
            config_source = config::createConfigSource(config);
            LOG_INFO(logger::get_logger(), "Created config source: {}", 
                    config_source->getDescription());
        } catch (const std::exception& e) {
            std::cerr << "FATAL: Failed to create config source: " << e.what() << std::endl;
            return 1;
        }

        // Load initial scene configuration
        SceneConfiguration scene_config;
        try {
            scene_config = config_source->load();
        } catch (const std::exception& e) {
            std::cerr << "FATAL: Failed to load scene configuration: " << e.what() << std::endl;
            return 1;
        }

        LOG_INFO(logger::get_logger(), "Scene configuration loaded successfully: {}",
                 (std::ostringstream{} << scene_config).str());

        // Fail early if no cameras are configured
        if (scene_config.cameras.empty()) {
            LOG_ERROR(logger::get_logger(),
                      "FATAL: No cameras configured. Update config/scenes.json 'cameras' list.");
            return 1;
        }

        // Validate SSL certificate paths if SSL is enabled
        if (config.mqtt.ssl.enabled) {
            bool cert_error = false;

            if (!std::filesystem::exists(config.mqtt.ssl.ca_cert_path)) {
                LOG_ERROR(logger::get_logger(), "SSL CA certificate not found: {}",
                          config.mqtt.ssl.ca_cert_path);
                cert_error = true;
            }

            if (!std::filesystem::exists(config.mqtt.ssl.client_cert_path)) {
                LOG_ERROR(logger::get_logger(), "SSL client certificate not found: {}",
                          config.mqtt.ssl.client_cert_path);
                cert_error = true;
            }

            if (!std::filesystem::exists(config.mqtt.ssl.client_key_path)) {
                LOG_ERROR(logger::get_logger(), "SSL client key not found: {}",
                          config.mqtt.ssl.client_key_path);
                cert_error = true;
            }

            if (cert_error) {
                LOG_ERROR(logger::get_logger(), "FATAL: SSL is enabled but one or more certificate "
                                                "files are missing or inaccessible");
                return 1;
            }

            LOG_INFO(logger::get_logger(), "SSL certificate validation passed");
        }

        auto& metricsManager = MetricsManager::getInstance(config.metrics);
        auto& traceManager = TraceManager::getInstance(config.tracing);
        MqttClient client(config.mqtt.server_address, config.mqtt.client_id, config.mqtt.ssl);
        Publisher publisher(client);

        // Use unique_ptr for MessageHandler to enable atomic swapping
        std::unique_ptr<MessageHandler> handler = std::make_unique<MessageHandler>(
            publisher, scene_config, config.time_chunking_fps, config.max_lag_seconds);
        std::mutex handler_mutex;

        // Set up thread-safe message processing callback
        client.set_message_callback(
            [&handler, &handler_mutex](const CameraDetectionMsg& detectionMsg) {
                std::lock_guard<std::mutex> lock(handler_mutex);
                if (handler) {
                    handler->handleDetectionMessage(detectionMsg);
                }
            });

        // Connect and subscribe
        client.connect();

        // Build list of topics from camera configurations
        std::vector<std::string> camera_topics;
        for (const auto& camera : scene_config.cameras) {
            std::string topic = "scenescape/data/camera/" + camera.id;
            camera_topics.push_back(topic);
        }

        // Subscribe to all camera topics
        if (!camera_topics.empty()) {
            client.subscribe(camera_topics, config.mqtt.qos);
        } else {
            LOG_WARNING(logger::get_logger(),
                        "No cameras configured, not subscribing to any topics");
        }

        // Start watching for config updates (SIGHUP for file, MQTT for API)
        config_source->startWatchingForUpdates(
            [&scene_config, &handler, &handler_mutex, &client, &publisher, &config](
                const SceneConfiguration& new_scene_config) -> bool {
                LOG_INFO(logger::get_logger(), "Config update detected, reloading...");

                try {
                    // Compute camera topic differences
                    std::vector<std::string> old_topics;
                    for (const auto& camera : scene_config.cameras) {
                        old_topics.push_back("scenescape/data/camera/" + camera.id);
                    }

                    std::vector<std::string> new_topics;
                    for (const auto& camera : new_scene_config.cameras) {
                        new_topics.push_back("scenescape/data/camera/" + camera.id);
                    }

                    // Find topics to unsubscribe
                    std::vector<std::string> topics_to_remove;
                    for (const auto& old_topic : old_topics) {
                        if (std::find(new_topics.begin(), new_topics.end(), old_topic) ==
                            new_topics.end()) {
                            topics_to_remove.push_back(old_topic);
                        }
                    }

                    // Find topics to subscribe
                    std::vector<std::string> topics_to_add;
                    for (const auto& new_topic : new_topics) {
                        if (std::find(old_topics.begin(), old_topics.end(), new_topic) ==
                            old_topics.end()) {
                            topics_to_add.push_back(new_topic);
                        }
                    }

                    // Build new handler atomically
                    auto new_handler = std::make_unique<MessageHandler>(
                        publisher, new_scene_config, config.time_chunking_fps,
                        config.max_lag_seconds);

                    // Atomic swap under lock
                    {
                        std::lock_guard<std::mutex> lock(handler_mutex);
                        handler = std::move(new_handler);
                    }

                    // Update MQTT subscriptions
                    if (!topics_to_remove.empty()) {
                        LOG_INFO(logger::get_logger(),
                                 "Unsubscribing from {} removed camera topics",
                                 topics_to_remove.size());
                        client.unsubscribe(topics_to_remove);
                    }

                    if (!topics_to_add.empty()) {
                        LOG_INFO(logger::get_logger(), "Subscribing to {} new camera topics",
                                 topics_to_add.size());
                        client.subscribe(topics_to_add, config.mqtt.qos);
                    }

                    // Update scene config
                    scene_config = new_scene_config;

                    LOG_INFO(logger::get_logger(), "Scene configuration reloaded successfully: {}",
                             (std::ostringstream{} << scene_config).str());

                    return true;
                } catch (const std::exception& e) {
                    LOG_ERROR(logger::get_logger(),
                              "Failed to reload scene configuration: {}", e.what());
                    return false;
                }
            });

        LOG_INFO(logger::get_logger(), "Waiting for messages...");

        // Main event loop - config source watches for updates in background
        while (client.is_connected()) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }

        // Cleanup
        config_source->stopWatching();
        client.disconnect();
        metricsManager.shutdown();
        traceManager.shutdown();
        publisher.stop();
    } catch (const std::exception& exc) {
        LOG_ERROR(logger::get_logger(), "Error: {}", exc.what());
        return 1;
    }

    return 0;
}
