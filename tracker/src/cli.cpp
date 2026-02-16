// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "cli.hpp"

#include "version.hpp"
#include <CLI/CLI.hpp>
#include <iostream>

namespace tracker {

CliConfig parse_cli_args(int argc, char* argv[]) {
    CliConfig config;

    CLI::App app{"Tracker Service v" + std::string(SERVICE_VERSION) + " (" + GIT_COMMIT + ")"};

    // Bootstrap options for Service mode
    app.add_option("-c,--config", config.config_path, "Path to JSON configuration file")
        ->check(CLI::ExistingFile);

    app.add_option("-s,--schema", config.schema_path, "Path to JSON schema for configuration")
        ->check(CLI::ExistingFile);

    // Healthcheck subcommand (CLI-only for simplicity)
    auto healthcheck_cmd = app.add_subcommand("healthcheck", "Query service health endpoint");
    healthcheck_cmd
        ->add_option("--port", config.healthcheck_port, "Port of healthcheck server to query")
        ->check(CLI::Range(1024, 65535))
        ->default_val(8080);
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
        // Require config and schema files in Service mode
        if (config.config_path.empty()) {
            std::cerr << "Error: --config is required in service mode\n";
            std::exit(1);
        }
        if (config.schema_path.empty()) {
            std::cerr << "Error: --schema is required in service mode\n";
            std::exit(1);
        }
    }

    return config;
}

} // namespace tracker
