// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <CLI/CLI.hpp>
#include <csignal>
#include <thread>

#include "logger.hpp"

namespace {
volatile std::sig_atomic_t g_shutdown_requested = 0;

void signal_handler(int signal) {
    g_shutdown_requested = 1;
}
} // namespace

int main(int argc, char* argv[]) {
    CLI::App app{"Tracker Service v" + std::string(tracker::SERVICE_VERSION) + " (" +
                 tracker::GIT_COMMIT + ")"};

    std::string log_level;
    app.add_option("-l,--log-level", log_level, "Log level (trace|debug|info|warn|error)")
        ->envname("LOG_LEVEL")
        ->default_str("info");

    CLI11_PARSE(app, argc, argv);

    // Initialize structured JSON logging
    tracker::Logger::init(log_level);

    // Setup signal handlers for graceful shutdown
    std::signal(SIGTERM, signal_handler);
    std::signal(SIGINT, signal_handler);

    LOG_INFO("Tracker service starting");

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

    tracker::Logger::shutdown();
    return 0;
}
