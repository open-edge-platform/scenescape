// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <thread>

#include "cli.hpp"
#include "healthcheck_command.hpp"
#include "healthcheck_server.hpp"
#include "logger.hpp"

#include <rv/tracking/TrackedObject.hpp>

namespace {
volatile std::sig_atomic_t g_shutdown_requested = 0;
std::atomic<bool> g_liveness{false};
std::atomic<bool> g_readiness{false};

void signal_handler(int signal) {
    g_shutdown_requested = 1;
}
} // namespace

int main(int argc, char* argv[]) {
    // Parse command-line arguments
    auto config = tracker::parse_cli_args(argc, argv);

    // Handle healthcheck subcommand (skip logger initialization for speed)
    if (config.mode == tracker::CliConfig::Mode::Healthcheck) {
        return tracker::run_healthcheck_command(config.healthcheck_endpoint,
                                                config.healthcheck_port);
    }

    // Main service mode - initialize logger
    tracker::Logger::init(config.log_level);

    // Setup signal handlers for graceful shutdown
    std::signal(SIGTERM, signal_handler);
    std::signal(SIGINT, signal_handler);

    LOG_INFO("Tracker service starting");

    // Minimal RobotVision usage for image size comparison
    rv::tracking::TrackedObject obj;
    LOG_INFO("RobotVision TrackedObject size: {}", sizeof(obj));

    // Start healthcheck server
    tracker::HealthcheckServer health_server(config.healthcheck_port, g_liveness, g_readiness);
    health_server.start();

    // Mark service as healthy
    // TODO: Set g_readiness = true only after MQTT connection succeeds
    g_liveness = true;
    g_readiness = true;

    // Main loop - log example messages every 3 seconds
    int iteration = 0;
    while (!g_shutdown_requested) {
        iteration++;

        // Example of simple structured logging with format string
        LOG_INFO("Service heartbeat - iteration {}", iteration);

        if (iteration % 2 == 0) {
            // Example with MQTT context
            LOG_DEBUG_ENTRY(tracker::LogEntry("MQTT message received")
                                .component("mqtt")
                                .operation("receive")
                                .mqtt({"scenescape/scene-01/detection", std::nullopt, "message"}));
        }

        if (iteration % 3 == 0) {
            // Example with domain context
            LOG_DEBUG_ENTRY(tracker::LogEntry("Processing detection")
                                .component("tracker")
                                .operation("process_detection")
                                .domain({.camera_id = "cam-01",
                                         .scene_id = "scene-main",
                                         .object_category = "person"}));
        }

        if (iteration % 5 == 0) {
            // Example with trace context
            LOG_TRACE_ENTRY(tracker::LogEntry("Detailed trace message")
                                .component("tracker")
                                .trace({"abc123", "span-456"}));
        }

        std::this_thread::sleep_for(std::chrono::seconds(3));
    }

    LOG_INFO("Tracker service shutting down gracefully");

    // Mark as not ready, stop healthcheck server
    g_readiness = false;
    g_liveness = false;
    health_server.stop();

    tracker::Logger::shutdown();
    return 0;
}
