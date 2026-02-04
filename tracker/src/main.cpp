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

#include <rv/tracking/TrackedObject.hpp>

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

    // Minimal RobotVision usage for image size comparison
    rv::tracking::TrackedObject obj;
    LOG_INFO("RobotVision TrackedObject size: {}", sizeof(obj));

    // Start healthcheck server
    tracker::HealthcheckServer health_server(config.infrastructure.tracker.healthcheck.port,
                                             g_liveness, g_readiness);
    health_server.start();

    // Mark service as live (process is running)
    g_liveness = true;

    // Initialize MQTT client
    g_mqtt_client = std::make_shared<tracker::MqttClient>(config.infrastructure.mqtt);

    // Initialize message handler with schema validation config
    auto message_handler = std::make_unique<tracker::MessageHandler>(
        g_mqtt_client, config.infrastructure.tracker.schema_validation,
        cli_config.schema_path.parent_path());

    // Connect to MQTT broker
    g_mqtt_client->connect();

    // Start message handler (subscribes to topics)
    message_handler->start();

    LOG_INFO("Tracker service running, waiting for messages...");

    // Main loop - update readiness based on MQTT state
    while (!g_shutdown_requested) {
        update_readiness();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    LOG_INFO("Tracker service shutting down gracefully");

    // Stop accepting new messages
    g_readiness = false;

    // Stop message handler first (uses MQTT client)
    message_handler->stop();
    message_handler.reset();

    // Reset MQTT client BEFORE logger shutdown to ensure disconnect logs work
    g_mqtt_client.reset();

    // Stop healthcheck server
    g_liveness = false;
    health_server.stop();

    // Shutdown logger last
    tracker::Logger::shutdown();
    return 0;
}
