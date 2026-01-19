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
    const auto this_file = std::filesystem::weakly_canonical(std::filesystem::path(__FILE__));
    const auto project_root = this_file.parent_path().parent_path().parent_path();
    return project_root / "schema" / "config.schema.json";
}
// Valid configuration tests
//

TEST(ConfigLoaderTest, LoadValidConfig) {
    TempFile config_file(R"({"log_level": "debug", "healthcheck_port": 9000})");

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.log_level, "debug");
    EXPECT_EQ(config.healthcheck_port, 9000);
}

TEST(ConfigLoaderTest, LoadAllLogLevelsAndPortBoundaries) {
    // Test all log levels
    for (const auto& level : {"trace", "debug", "info", "warn", "error"}) {
        TempFile config_file(R"({"log_level": ")" + std::string(level) +
                             R"(", "healthcheck_port": 8080})");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, level);
    }

    // Test port boundaries
    {
        TempFile config_file(R"({"log_level": "info", "healthcheck_port": 1024})");
        EXPECT_EQ(load_config(config_file.path(), get_schema_path()).healthcheck_port, 1024);
    }
    {
        TempFile config_file(R"({"log_level": "info", "healthcheck_port": 65535})");
        EXPECT_EQ(load_config(config_file.path(), get_schema_path()).healthcheck_port, 65535);
    }
}

//
// Environment variable override tests
//

TEST(ConfigLoaderTest, EnvOverrides) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");

    // Override log level only
    {
        ScopedEnv env("TRACKER_LOG_LEVEL", "trace");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, "trace");
        EXPECT_EQ(config.healthcheck_port, 8080);
    }

    // Override port only
    {
        ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "9999");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, "info");
        EXPECT_EQ(config.healthcheck_port, 9999);
    }

    // Override both
    {
        ScopedEnv env_level("TRACKER_LOG_LEVEL", "error");
        ScopedEnv env_port("TRACKER_HEALTHCHECK_PORT", "5000");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, "error");
        EXPECT_EQ(config.healthcheck_port, 5000);
    }
}

//
// Error handling tests
//

TEST(ConfigLoaderTest, MissingFilesThrow) {
    TempFile valid_config(R"({"log_level": "info", "healthcheck_port": 8080})");

    EXPECT_THROW(load_config("/nonexistent/config.json", get_schema_path()), std::runtime_error);
    EXPECT_THROW(load_config(valid_config.path(), "/nonexistent/schema.json"), std::runtime_error);
}

TEST(ConfigLoaderTest, InvalidJsonThrows) {
    // Invalid config JSON
    {
        TempFile config_file(R"({invalid json})");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }

    // Invalid schema JSON (covers lines 34-35)
    {
        TempFile valid_config(R"({"log_level": "info", "healthcheck_port": 8080})");
        TempFile bad_schema(R"({not valid json)");
        EXPECT_THROW(load_config(valid_config.path(), bad_schema.path()), std::runtime_error);
    }
}

TEST(ConfigLoaderTest, SchemaValidationErrors) {
    // Missing required fields
    EXPECT_THROW(load_config(TempFile(R"({"healthcheck_port": 8080})").path(), get_schema_path()),
                 std::runtime_error);
    EXPECT_THROW(load_config(TempFile(R"({"log_level": "info"})").path(), get_schema_path()),
                 std::runtime_error);

    // Invalid log level
    EXPECT_THROW(
        load_config(TempFile(R"({"log_level": "invalid", "healthcheck_port": 8080})").path(),
                    get_schema_path()),
        std::runtime_error);

    // Port out of range
    EXPECT_THROW(load_config(TempFile(R"({"log_level": "info", "healthcheck_port": 1023})").path(),
                             get_schema_path()),
                 std::runtime_error);
    EXPECT_THROW(load_config(TempFile(R"({"log_level": "info", "healthcheck_port": 65536})").path(),
                             get_schema_path()),
                 std::runtime_error);

    // Extra properties not allowed
    EXPECT_THROW(
        load_config(
            TempFile(R"({"log_level": "info", "healthcheck_port": 8080, "extra": "value"})").path(),
            get_schema_path()),
        std::runtime_error);
}

TEST(ConfigLoaderTest, EnvValidationErrors) {
    TempFile config_file(R"({"log_level": "info", "healthcheck_port": 8080})");

    // Invalid log level
    {
        ScopedEnv env("TRACKER_LOG_LEVEL", "invalid_level");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }

    // Non-numeric port
    {
        ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "not_a_number");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }

    // Port out of range (too low, too high, overflow)
    {
        ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "1000");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }
    {
        ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "70000");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }
    // Covers std::out_of_range (lines 96-97)
    {
        ScopedEnv env("TRACKER_HEALTHCHECK_PORT", "99999999999999999999");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }
}

} // namespace
} // namespace tracker
