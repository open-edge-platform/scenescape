// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "cli.hpp"

#include "logger.hpp"
#include <CLI/CLI.hpp>

namespace tracker {

CliConfig parse_cli_args(int argc, char* argv[]) {
    CliConfig config;

    CLI::App app{"Tracker Service v" + std::string(SERVICE_VERSION) + " (" + GIT_COMMIT + ")"};

    // Global options
    app.add_option("-l,--log-level", config.log_level, "Log level (trace|debug|info|warn|error)")
        ->envname("LOG_LEVEL")
        ->default_str("info");

    app.add_option("--healthcheck-port", config.healthcheck_port, "Healthcheck server port")
        ->envname("HEALTHCHECK_PORT")
        ->check(CLI::Range(1024, 65535))
        ->default_val(8080);

    // Healthcheck subcommand
    auto healthcheck_cmd = app.add_subcommand("healthcheck", "Query service health endpoint");
    healthcheck_cmd
        ->add_option("--endpoint", config.healthcheck_endpoint, "Health endpoint to query")
        ->default_str("/readyz");

    try {
        app.parse(argc, argv);
    } catch (const CLI::ParseError& e) {
        std::exit(app.exit(e));
    }

    // Determine mode
    if (healthcheck_cmd->parsed()) {
        config.mode = CliConfig::Mode::Healthcheck;
    } else {
        config.mode = CliConfig::Mode::Service;
    }

    return config;
}

} // namespace tracker
