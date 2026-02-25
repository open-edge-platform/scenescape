// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <thread>

#include "cli.hpp"
#include "config_loader.hpp"
#include "healthcheck_command.hpp"
#include "healthcheck_server.hpp"
#include "logger.hpp"
#include "message_handler.hpp"
#include "mqtt_client.hpp"
#include "scene_loader.hpp"
#include "scene_registry.hpp"
#include "time_chunk_buffer.hpp"
#include "time_chunk_scheduler.hpp"
#include "track_publisher.hpp"

namespace {
volatile std::sig_atomic_t g_shutdown_requested = 0;
std::atomic<bool> g_liveness{false};
std::atomic<bool> g_readiness{false};
std::shared_ptr<tracker::MqttClient> g_mqtt_client;

void signal_handler(int signal) {
    g_shutdown_requested = 1;
}

void update_readiness() {
    if (g_mqtt_client) {
        g_readiness = g_mqtt_client->isConnected() && g_mqtt_client->isSubscribed();
    } else {
        g_readiness = false;
    }
}
} // namespace

int main(int argc, char* argv[]) {
    // Parse command-line arguments (bootstrap only)
    auto cli_config = tracker::parse_cli_args(argc, argv);

    // Handle healthcheck subcommand
    if (cli_config.mode == tracker::CliConfig::Mode::Healthcheck) {
        return tracker::run_healthcheck_command(cli_config.healthcheck_endpoint,
                                                cli_config.healthcheck_port);
    }

    // Load and validate service configuration from JSON file
    tracker::ServiceConfig config;
    try {
        config = tracker::load_config(cli_config.config_path, cli_config.schema_path);
    } catch (const std::exception& e) {
        std::cerr << "Configuration error: " << e.what() << "\n";
        return 1;
    }

    // Main service mode - initialize logger
    tracker::Logger::init(config.observability.logging.level);

    // Setup signal handlers for graceful shutdown
    std::signal(SIGTERM, signal_handler);
    std::signal(SIGINT, signal_handler);

    LOG_INFO("Tracker service starting");

    // Start healthcheck server
    tracker::HealthcheckServer health_server(config.infrastructure.tracker.healthcheck.port,
                                             g_liveness, g_readiness);
    health_server.start();

    // Mark service as live (process is running)
    g_liveness = true;

    // Load scenes using appropriate loader based on config
    std::vector<tracker::Scene> scenes;
    try {
        auto scene_loader =
            tracker::create_scene_loader(config.scenes, cli_config.config_path.parent_path());
        scenes = scene_loader->load();
    } catch (const std::exception& e) {
        LOG_ERROR("Failed to load scenes: {}", e.what());
        return 1;
    }

    // Initialize scene registry from loaded scenes
    tracker::SceneRegistry scene_registry;
    if (!scenes.empty()) {
        try {
            scene_registry.register_scenes(scenes);
            LOG_INFO("Loaded {} scenes with {} cameras", scene_registry.scene_count(),
                     scene_registry.camera_count());
        } catch (const tracker::DuplicateCameraError& e) {
            LOG_ERROR("Scene configuration error: {}", e.what());
            return 1;
        } catch (const std::exception& e) {
            LOG_ERROR("Failed to register scenes: {}", e.what());
            return 1;
        }
    }

    // Initialize MQTT client
    g_mqtt_client = std::make_shared<tracker::MqttClient>(config.infrastructure.mqtt);

    // Initialize time chunk buffer and tracking pipeline
    tracker::TimeChunkBuffer chunk_buffer;

    // Initialize track publisher
    auto track_publisher = std::make_shared<tracker::TrackPublisher>(g_mqtt_client);

    // Create publish callback for workers
    tracker::PublishCallback publish_callback =
        [track_publisher](const std::string& scene_id, const std::string& scene_name,
                          const std::string& category, const std::string& timestamp,
                          const std::vector<tracker::Track>& tracks) {
            track_publisher->publish(scene_id, scene_name, category, timestamp, tracks);
        };

    // Initialize time chunk scheduler with workers
    auto scheduler = std::make_unique<tracker::TimeChunkScheduler>(
        chunk_buffer, scene_registry, config.tracking, publish_callback);

    // Initialize message handler with buffer integration
    auto message_handler = std::make_unique<tracker::MessageHandler>(
        g_mqtt_client, scene_registry, chunk_buffer, config.tracking,
        config.infrastructure.tracker.schema_validation, cli_config.schema_path.parent_path());

    // Connect to MQTT broker.
    // Sync failures (broker unreachable) throw immediately.
    // Async failures (auth, protocol) set exitCode() and are caught in the main loop.
    try {
        g_mqtt_client->connect();
    } catch (const std::exception& e) {
        LOG_ERROR("MQTT connection failed: {}", e.what());
        return g_mqtt_client->exitCode();
    }

    // Start scheduler before message handler (ready to receive)
    scheduler->start();

    // Start message handler (subscribes to topics)
    message_handler->start();

    LOG_INFO("Tracker service running (chunking @ {}fps, max_workers={})",
             config.tracking.time_chunking_rate_fps, config.tracking.max_workers);

    // Main loop - update readiness based on MQTT state
    while (!g_shutdown_requested && g_mqtt_client->exitCode() < 0) {
        update_readiness();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    // Determine exit code: async connect failure or graceful shutdown
    int exit_code = 0;
    if (g_mqtt_client->exitCode() >= 0) {
        exit_code = g_mqtt_client->exitCode();
        LOG_ERROR("MQTT connect failure — exiting with code {}", exit_code);
    } else {
        LOG_INFO("Tracker service shutting down gracefully");
    }

    // Flush logs to ensure shutdown message is visible
    if (auto* logger = tracker::Logger::get()) {
        logger->flush_log();
    }

    // Stop accepting new messages
    g_readiness = false;

    // Stop message handler first (stops pushing to buffer)
    message_handler->stop();
    message_handler.reset();

    // Stop scheduler (sends sentinels to workers, waits for them to finish)
    scheduler->stop();
    scheduler.reset();

    // Clear the publish callback to release its captured shared_ptr to track_publisher
    // This is necessary because std::function captures by value
    publish_callback = nullptr;

    // Reset track publisher to release its reference to MQTT client
    // This must happen BEFORE g_mqtt_client.reset() and Logger::shutdown()
    // to ensure MqttClient::disconnect() logging works correctly
    track_publisher.reset();

    // Reset MQTT client BEFORE logger shutdown to ensure disconnect logs work
    g_mqtt_client.reset();

    // Stop healthcheck server
    g_liveness = false;
    health_server.stop();

    // Shutdown logger last
    tracker::Logger::shutdown();
    return exit_code;
}
