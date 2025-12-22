#pragma once

#include <CLI/CLI.hpp>
#include "config.h"

namespace config_args {
// Parse CLI and environment, validate against schema if present, and return Config.
// On --help or parse errors, this function will print help and exit with the appropriate code.
// Throws std::runtime_error on missing or invalid configuration.
Config load_config_from_argv(int argc, char* argv[]);
}

// Register CLI11 options mapping to Config. If with_env_names is true, attach env overlays.
void register_cli_options(CLI::App &app, Config &cfg, bool with_env_names);

// Add a non-configurable --config and --schema to main app to keep strict parsing.
void register_dummy_config_options(CLI::App &app, std::string &config_path, std::string &schema_path);
