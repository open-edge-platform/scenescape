// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "cli.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
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
 * @brief RAII helper for creating temporary files.
 */
class TempFile {
public:
    TempFile(const std::string& content = "{}") {
        path_ = std::filesystem::temp_directory_path() /
                ("tracker_cli_test_" + std::to_string(counter_++) + ".json");
        std::ofstream ofs(path_);
        ofs << content;
    }

    ~TempFile() { std::filesystem::remove(path_); }

    std::string path_str() const { return path_.string(); }

private:
    std::filesystem::path path_;
    static inline int counter_ = 0;
};

//
// Service mode tests
//

/**
 * @brief Test service mode with valid config and schema files.
 */
TEST(CliTest, ServiceModeWithConfigAndSchema) {
    TempFile config_file;
    TempFile schema_file;
    ArgvHelper helper(
        {"tracker", "--config", config_file.path_str(), "--schema", schema_file.path_str()});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Service);
    EXPECT_EQ(config.config_path, config_file.path_str());
    EXPECT_EQ(config.schema_path, schema_file.path_str());
}

/**
 * @brief Test service mode with short options.
 */
TEST(CliTest, ServiceModeWithShortOptions) {
    TempFile config_file;
    TempFile schema_file;
    ArgvHelper helper({"tracker", "-c", config_file.path_str(), "-s", schema_file.path_str()});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Service);
    EXPECT_EQ(config.config_path, config_file.path_str());
    EXPECT_EQ(config.schema_path, schema_file.path_str());
}

/**
 * @brief Test service mode without config file exits with error.
 */
TEST(CliTest, ServiceModeWithoutConfigExits) {
    TempFile schema_file;
    ArgvHelper helper({"tracker", "--schema", schema_file.path_str()});
    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(1), "");
}

/**
 * @brief Test service mode without schema file exits with error.
 */
TEST(CliTest, ServiceModeWithoutSchemaExits) {
    TempFile config_file;
    ArgvHelper helper({"tracker", "--config", config_file.path_str()});
    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(1), "");
}

/**
 * @brief Test service mode without any args exits with error.
 */
TEST(CliTest, ServiceModeWithoutArgsExits) {
    ArgvHelper helper({"tracker"});
    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(1), "");
}

/**
 * @brief Test service mode with non-existent config file exits with error.
 */
TEST(CliTest, ServiceModeWithNonExistentConfigExits) {
    TempFile schema_file;
    ArgvHelper helper(
        {"tracker", "--config", "/nonexistent/config.json", "--schema", schema_file.path_str()});
    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(105), "");
}

//
// Healthcheck subcommand tests
//

/**
 * @brief Test healthcheck subcommand mode detection and defaults.
 */
TEST(CliTest, HealthcheckSubcommandDefaults) {
    ArgvHelper helper({"tracker", "healthcheck"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Healthcheck);
    EXPECT_EQ(config.healthcheck_endpoint, "/readyz");
    EXPECT_EQ(config.healthcheck_port, 8080);
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
 * @brief Test healthcheck subcommand with custom port.
 */
TEST(CliTest, HealthcheckSubcommandWithPort) {
    ArgvHelper helper({"tracker", "healthcheck", "--port", "9090"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Healthcheck);
    EXPECT_EQ(config.healthcheck_port, 9090);
}

/**
 * @brief Test healthcheck subcommand with all options.
 */
TEST(CliTest, HealthcheckSubcommandWithAllOptions) {
    ArgvHelper helper({"tracker", "healthcheck", "--port", "7777", "--endpoint", "/livez"});
    auto config = parse_cli_args(helper.argc(), helper.argv());

    EXPECT_EQ(config.mode, CliConfig::Mode::Healthcheck);
    EXPECT_EQ(config.healthcheck_port, 7777);
    EXPECT_EQ(config.healthcheck_endpoint, "/livez");
}

/**
 * @brief Test healthcheck port boundary values.
 */
TEST(CliTest, HealthcheckPortBoundaries) {
    // Minimum valid (1024)
    {
        ArgvHelper helper({"tracker", "healthcheck", "--port", "1024"});
        auto config = parse_cli_args(helper.argc(), helper.argv());
        EXPECT_EQ(config.healthcheck_port, 1024);
    }

    // Maximum valid (65535)
    {
        ArgvHelper helper({"tracker", "healthcheck", "--port", "65535"});
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
        ArgvHelper helper({"tracker", "healthcheck", "--port", "1023"});
        EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(105),
                    "");
    }

    // Above range (65536)
    {
        ArgvHelper helper({"tracker", "healthcheck", "--port", "65536"});
        EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(105),
                    "");
    }
}

/**
 * @brief Test healthcheck port with non-numeric value exits with error.
 */
TEST(CliTest, HealthcheckPortNonNumeric) {
    ArgvHelper helper({"tracker", "healthcheck", "--port", "abc"});
    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(105), "");
}

//
// General CLI tests
//

/**
 * @brief Test help flag exits gracefully.
 */
TEST(CliTest, HelpFlag) {
    ArgvHelper helper({"tracker", "--help"});
    EXPECT_EXIT(parse_cli_args(helper.argc(), helper.argv()), ::testing::ExitedWithCode(0), "");
}

/**
 * @brief Test healthcheck help flag exits gracefully.
 */
TEST(CliTest, HealthcheckHelpFlag) {
    ArgvHelper helper({"tracker", "healthcheck", "--help"});
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
 * @brief Test healthcheck subcommand does not require config or schema files.
 */
TEST(CliTest, HealthcheckDoesNotRequireConfigOrSchema) {
    ArgvHelper helper({"tracker", "healthcheck"});
    // Should not exit, config/schema are not required for healthcheck mode
    auto config = parse_cli_args(helper.argc(), helper.argv());
    EXPECT_EQ(config.mode, CliConfig::Mode::Healthcheck);
    EXPECT_TRUE(config.config_path.empty());
    EXPECT_TRUE(config.schema_path.empty());
}

} // namespace
} // namespace tracker
