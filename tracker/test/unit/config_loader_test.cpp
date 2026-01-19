// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>

namespace tracker {
namespace {

/**
 * @brief RAII helper for setting/unsetting environment variables.
 */
class ScopedEnv {
public:
    ScopedEnv(const char* name, const char* value) : name_(name) {
        const char* old = std::getenv(name);
        if (old) {
            old_value_ = old;
            had_old_ = true;
        }
        setenv(name, value, 1);
    }

    ~ScopedEnv() {
        if (had_old_) {
            setenv(name_, old_value_.c_str(), 1);
        } else {
            unsetenv(name_);
        }
    }

private:
    const char* name_;
    std::string old_value_;
    bool had_old_ = false;
};

/**
 * @brief RAII helper for creating temporary files.
 */
class TempFile {
public:
    TempFile(const std::string& content, const std::string& suffix = ".json") {
        path_ = std::filesystem::temp_directory_path() /
                ("tracker_test_" + std::to_string(counter_++) + suffix);
        std::ofstream ofs(path_);
        ofs << content;
    }

    ~TempFile() { std::filesystem::remove(path_); }

    const std::filesystem::path& path() const { return path_; }

private:
    std::filesystem::path path_;
    static inline int counter_ = 0;
};

/**
 * @brief Get path to the schema file (production schema used in tests).
 */
std::filesystem::path get_schema_path() {
    // Navigate from test file to tracker/schema/config.schema.json
    return std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() / "schema" /
           "config.schema.json";
}

//
// Valid configuration tests
//

TEST(ConfigLoaderTest, LoadValidConfig) {
    TempFile config_file(R"({
        "log_level": "debug",
        "healthcheck_port": 9000
    })");

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.log_level, "debug");
    EXPECT_EQ(config.healthcheck_port, 9000);
}

TEST(ConfigLoaderTest, LoadAllLogLevels) {
    for (const auto& level : {"trace", "debug", "info", "warn", "error"}) {
        TempFile config_file(R"({"log_level": ")" + std::string(level) +
                             R"(", "healthcheck_port": 8080})");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, level);
    }
}

TEST(ConfigLoaderTest, LoadPortBoundaries) {
    // Minimum valid port
    {
        TempFile config_file(R"({"log_level": "info", "healthcheck_port": 1024})");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.healthcheck_port, 1024);
    }

    // Maximum valid port
    {
        TempFile config_file(R"({"log_level": "info", "healthcheck_port": 65535})");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.healthcheck_port, 65535);
    }
}

//
// Environment variable override tests
//

TEST(ConfigLoaderTest, EnvOverrideLogLevel) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");
    ScopedEnv env("TRACKER_LOG_LEVEL", "trace");

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.log_level, "trace");
    EXPECT_EQ(config.healthcheck_port, 8080);
}

TEST(ConfigLoaderTest, EnvOverrideHealthcheckPort) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");
    ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "9999");

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.log_level, "info");
    EXPECT_EQ(config.healthcheck_port, 9999);
}

TEST(ConfigLoaderTest, EnvOverrideBothValues) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");
    ScopedEnv env_level("TRACKER_LOG_LEVEL", "error");
    ScopedEnv env_port("TRACKER_HEALTHCHECK_PORT", "5000");

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.log_level, "error");
    EXPECT_EQ(config.healthcheck_port, 5000);
}

//
// Error handling tests - missing/invalid files
//

TEST(ConfigLoaderTest, MissingConfigFileThrows) {
    EXPECT_THROW(load_config("/nonexistent/path/config.json", get_schema_path()),
                 std::runtime_error);
}

TEST(ConfigLoaderTest, MissingSchemaFileThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");

    EXPECT_THROW(load_config(config_file.path(), "/nonexistent/schema.json"), std::runtime_error);
}

TEST(ConfigLoaderTest, InvalidJsonThrows) {
    TempFile config_file(R"({invalid json})");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

//
// Schema validation error tests
//

TEST(ConfigLoaderTest, MissingLogLevelThrows) {
    TempFile config_file(R"({"healthcheck_port": 8080})");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, MissingHealthcheckPortThrows) {
    TempFile config_file(R"({"log_level": "info"})");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, InvalidLogLevelThrows) {
    TempFile config_file(R"({"log_level": "invalid", "healthcheck_port": 8080})");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, PortTooLowThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 1023})");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, PortTooHighThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 65536})");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, ExtraPropertiesThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080, "extra": "value"})");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

//
// Environment variable validation error tests
//

TEST(ConfigLoaderTest, InvalidEnvLogLevelThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");
    ScopedEnv env("TRACKER_LOG_LEVEL", "invalid_level");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, InvalidEnvPortThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");
    ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "not_a_number");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, EnvPortTooLowThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");
    ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "1000");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, EnvPortTooHighThrows) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");
    ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "70000");

    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

} // namespace
} // namespace tracker
