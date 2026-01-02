// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <CLI/CLI.hpp>

#include "logger.hpp"

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

    LOG_INFO("Tracker service starting");

    // Example of structured logging with context
    LOG_INFO_ENTRY(tracker::LogEntry("MQTT client connected")
                       .component("mqtt")
                       .operation("connect")
                       .mqtt({"scenescape/+/detection", std::nullopt, "subscribe"}));

    // Example with domain context
    LOG_DEBUG_ENTRY(
        tracker::LogEntry("Processing detection")
            .component("tracker")
            .operation("process_detection")
            .domain(
                {.camera_id = "cam-01", .scene_id = "scene-main", .object_category = "person"}));

    // Example with trace context
    LOG_TRACE_ENTRY(tracker::LogEntry("Detailed trace message")
                        .component("tracker")
                        .trace({"abc123", "span-456"}));

    // Example error with context
    LOG_ERROR_ENTRY(tracker::LogEntry("Failed to process message")
                        .component("mqtt")
                        .operation("process")
                        .error({"ParseError", "Invalid JSON payload"}));

    LOG_INFO("Tracker service stopped");

    tracker::Logger::shutdown();
    return 0;
}
