// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <filesystem>
#include <string>

namespace tracker {

/**
 * @brief Service configuration loaded from JSON config file.
 *
 * Values can be overridden by environment variables with TRACKER_ prefix.
 */
struct ServiceConfig {
    std::string log_level;
    int healthcheck_port;
};

/// JSON Pointer paths (RFC6901) for extracting ServiceConfig values
namespace json {
constexpr char LOG_LEVEL[] = "/observability/logging/level";
constexpr char HEALTHCHECK_PORT[] = "/infrastructure/tracker/healthcheck/port";
} // namespace json

/**
 * @brief Load and validate service configuration from JSON file.
 *
 * Configuration layering (priority: high to low):
 * 1. Environment variables (TRACKER_LOG_LEVEL, TRACKER_HEALTHCHECK_PORT)
 * 2. JSON configuration file
 *
 * @param config_path Path to the JSON configuration file
 * @param schema_path Path to the JSON schema file
 * @return ServiceConfig Validated configuration
 *
 * @throws std::runtime_error if config file not found, invalid JSON, or schema validation fails
 */
ServiceConfig load_config(const std::filesystem::path& config_path,
                          const std::filesystem::path& schema_path);

} // namespace tracker
