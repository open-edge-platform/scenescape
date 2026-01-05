// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <string>

namespace tracker {

/**
 * @brief Command-line interface configuration result.
 */
struct CliConfig {
    enum class Mode {
        Service,    ///< Run main service
        Healthcheck ///< Run healthcheck command
    };

    Mode mode = Mode::Service;
    std::string log_level = "info";
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
