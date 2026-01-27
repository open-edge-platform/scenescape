// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <filesystem>
#include <string>

namespace tracker {

/**
 * @brief Command-line interface configuration for bootstrap.
 *
 * Contains only bootstrap options needed before config file loading.
 * Service configuration comes from JSON config file (see config_loader.hpp).
 */
struct CliConfig {
    enum class Mode {
        Service,    ///< Run main service
        Healthcheck ///< Run healthcheck command
    };

    Mode mode = Mode::Service;

    /// Path to JSON config file (required in Service mode)
    std::filesystem::path config_path;

    /// Path to JSON schema file (required in Service mode)
    std::filesystem::path schema_path;

    /// Healthcheck subcommand options (CLI-only for simplicity)
    int healthcheck_port = 8080;
    std::string healthcheck_endpoint = "/readyz";
};

/**
 * @brief Parse command-line arguments and configure application.
 *
 * @param argc Argument count
 * @param argv Argument values
 * @return CliConfig Parsed configuration
 *
 * @throws CLI::ParseError on invalid arguments or --help
 */
CliConfig parse_cli_args(int argc, char* argv[]);

} // namespace tracker
