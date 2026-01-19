// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "cli.hpp"

#include <cstdlib>
#include <gtest/gtest.h>
#include <vector>

namespace tracker {
namespace {

/**
 * @brief Helper to convert string vector to argc/argv format.
 */
class ArgvHelper {
public:
    ArgvHelper(const std::vector<std::string>& args) {
        for (const auto& arg : args) {
            args_.push_back(arg);
        }
        argv_.reserve(args_.size());
        for (auto& arg : args_) {
            argv_.push_back(&arg[0]);
        }
    }

    int argc() const { return static_cast<int>(argv_.size()); }
    char** argv() { return argv_.data(); }

private:
    std::vector<std::string> args_;
    std::vector<char*> argv_;
};

/**
 * @brief Test default values when no arguments provided.
 */
TEST(CliTest, DefaultValues) {
    ArgvHelper helper({"tracker"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Service);
    EXPECT_EQ(config.log_level, "info");
    EXPECT_EQ(config.healthcheck_port, 8080);
    EXPECT_EQ(config.healthcheck_endpoint, "/readyz");
}

/**
 * @brief Test log level parsing with short/long options and all valid levels.
 */
TEST(CliTest, LogLevelParsing) {
    // Short option
    {
        ArgvHelper helper({"tracker", "-l", "debug"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.log_level, "debug");
    }

    // Long option
    {
        ArgvHelper helper({"tracker", "--log-level", "trace"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.log_level, "trace");
    }

    // All valid log levels
    for (const auto& level : {"trace", "debug", "info", "warn", "error"}) {
        ArgvHelper helper({"tracker", "--log-level", level});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.log_level, level) << "Failed for log level: " << level;
    }
}

/**
 * @brief Test healthcheck port parsing with valid values including boundaries.
 */
TEST(CliTest, HealthcheckPortValidValues) {
    // Standard port
    {
        ArgvHelper helper({"tracker", "--healthcheck-port", "9090"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.healthcheck_port, 9090);
    }

    // Minimum valid (1024)
    {
        ArgvHelper helper({"tracker", "--healthcheck-port", "1024"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.healthcheck_port, 1024);
    }

    // Maximum valid (65535)
    {
        ArgvHelper helper({"tracker", "--healthcheck-port", "65535"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.healthcheck_port, 65535);
    }
}

/**
 * @brief Test healthcheck port rejects out-of-range values.
 */
TEST(CliTest, HealthcheckPortOutOfRange) {
    // Below range (1023)
    {
        ArgvHelper helper({"tracker", "--healthcheck-port", "1023"});
        EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(105),
                    "");
    }

    // Above range (65536)
    {
        ArgvHelper helper({"tracker", "--healthcheck-port", "65536"});
        EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(105),
                    "");
    }
}

/**
 * @brief Test healthcheck port with non-numeric value exits with error.
 */
TEST(CliTest, HealthcheckPortNonNumeric) {
    ArgvHelper helper({"tracker", "--healthcheck-port", "abc"});
    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(105), "");
}

/**
 * @brief Test healthcheck subcommand mode detection and default endpoint.
 */
TEST(CliTest, HealthcheckSubcommandDefaults) {
    ArgvHelper helper({"tracker", "healthcheck"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Healthcheck);
    EXPECT_EQ(config.healthcheck_endpoint, "/readyz");
}

/**
 * @brief Test healthcheck subcommand with custom endpoint.
 */
TEST(CliTest, HealthcheckSubcommandWithEndpoint) {
    ArgvHelper helper({"tracker", "healthcheck", "--endpoint", "/healthz"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Healthcheck);
    EXPECT_EQ(config.healthcheck_endpoint, "/healthz");
}

/**
 * @brief Test combining multiple options.
 */
TEST(CliTest, CombinedOptions) {
    ArgvHelper helper({"tracker", "--log-level", "warn", "--healthcheck-port", "8888"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Service);
    EXPECT_EQ(config.log_level, "warn");
    EXPECT_EQ(config.healthcheck_port, 8888);
}

/**
 * @brief Test environment variables for configuration.
 */
TEST(CliTest, EnvironmentVariables) {
    // LOG_LEVEL env var
    {
        setenv("LOG_LEVEL", "error", 1);
        ArgvHelper helper({"tracker"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.log_level, "error");
        unsetenv("LOG_LEVEL");
    }

    // HEALTHCHECK_PORT env var
    {
        setenv("HEALTHCHECK_PORT", "7070", 1);
        ArgvHelper helper({"tracker"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.healthcheck_port, 7070);
        unsetenv("HEALTHCHECK_PORT");
    }

    // CLI overrides env var
    {
        setenv("LOG_LEVEL", "error", 1);
        ArgvHelper helper({"tracker", "--log-level", "debug"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.log_level, "debug");
        unsetenv("LOG_LEVEL");
    }
}

/**
 * @brief Test help flag exits gracefully.
 */
TEST(CliTest, HelpFlag) {
    ArgvHelper helper({"tracker", "--help"});

    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(0), "");
}

/**
 * @brief Test invalid option exits with error.
 */
TEST(CliTest, InvalidOption) {
    ArgvHelper helper({"tracker", "--invalid-option"});

    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(109), "");
}

/**
 * @brief Test healthcheck subcommand with global options.
 */
TEST(CliTest, HealthcheckWithGlobalOptions) {
    ArgvHelper helper({"tracker", "--healthcheck-port", "9999", "healthcheck"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Healthcheck);
    EXPECT_EQ(config.healthcheck_port, 9999);
}

} // namespace
} // namespace tracker
