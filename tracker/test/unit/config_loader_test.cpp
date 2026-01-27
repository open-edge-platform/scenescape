// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"

#include "env_vars.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>
#include <optional>

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
        }
        setenv(name, value, 1);
    }

    ~ScopedEnv() {
        if (old_value_) {
            setenv(name_, old_value_->c_str(), 1);
        } else {
            unsetenv(name_);
        }
    }

private:
    const char* name_;
    std::optional<std::string> old_value_;
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

// Minimal valid config JSON (infrastructure.mqtt is required)
const char* MINIMAL_CONFIG = R"({
  "infrastructure": {
    "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
  }
})";

// Helper to create config with observability.logging.level
std::string config_with_log_level(const std::string& level) {
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      },
      "observability": {"logging": {"level": ")" +
           level + R"("}}
    })";
}

// Helper to create config with infrastructure.tracker.healthcheck.port
std::string config_with_port(int port) {
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true},
        "tracker": {"healthcheck": {"port": )" +
           std::to_string(port) + R"(}}
      }
    })";
}

// Helper to create config with both log level and port
std::string config_with_level_and_port(const std::string& level, int port) {
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true},
        "tracker": {"healthcheck": {"port": )" +
           std::to_string(port) + R"(}}
      },
      "observability": {"logging": {"level": ")" +
           level + R"("}}
    })";
}

TEST(ConfigLoaderTest, LoadValidConfig) {
    TempFile config_file(config_with_level_and_port("debug", 9000));

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.log_level, "debug");
    EXPECT_EQ(config.healthcheck_port, 9000);
}

TEST(ConfigLoaderTest, LoadAllLogLevelsAndPortBoundaries) {
    // Test all log levels (schema uses "warning" not "warn")
    for (const auto& level : {"trace", "debug", "info", "warning", "error"}) {
        TempFile config_file(config_with_log_level(level));
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, level);
    }

    // Test port boundaries
    {
        TempFile config_file(config_with_port(1024));
        EXPECT_EQ(load_config(config_file.path(), get_schema_path()).healthcheck_port, 1024);
    }
    {
        TempFile config_file(config_with_port(65535));
        EXPECT_EQ(load_config(config_file.path(), get_schema_path()).healthcheck_port, 65535);
    }
}

TEST(ConfigLoaderTest, DefaultValues) {
    // Minimal config should use defaults: log_level="info", healthcheck_port=8080
    TempFile config_file(MINIMAL_CONFIG);
    auto config = load_config(config_file.path(), get_schema_path());
    EXPECT_EQ(config.log_level, "info");
    EXPECT_EQ(config.healthcheck_port, 8080);
}

//
// Environment variable override tests
//

TEST(ConfigLoaderTest, EnvOverrides) {
    TempFile config_file(config_with_level_and_port("info", 8080));

    // Override log level only
    {
        ScopedEnv env(tracker::env::LOG_LEVEL, "trace");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, "trace");
        EXPECT_EQ(config.healthcheck_port, 8080);
    }

    // Override port only
    {
        ScopedEnv env(tracker::env::HEALTHCHECK_PORT, "9999");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, "info");
        EXPECT_EQ(config.healthcheck_port, 9999);
    }

    // Override both
    {
        ScopedEnv env_level(tracker::env::LOG_LEVEL, "error");
        ScopedEnv env_port(tracker::env::HEALTHCHECK_PORT, "5000");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.log_level, "error");
        EXPECT_EQ(config.healthcheck_port, 5000);
    }
}

//
// Error handling tests
//

TEST(ConfigLoaderTest, MissingFilesThrow) {
    TempFile valid_config(MINIMAL_CONFIG);

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
        TempFile valid_config(MINIMAL_CONFIG);
        TempFile bad_schema(R"({not valid json)");
        EXPECT_THROW(load_config(valid_config.path(), bad_schema.path()), std::runtime_error);
    }
}

TEST(ConfigLoaderTest, SchemaValidationErrors) {
    // Missing required infrastructure.mqtt
    {
        TempFile empty_config(R"({})");
        EXPECT_THROW(load_config(empty_config.path(), get_schema_path()), std::runtime_error);
    }
    {
        TempFile missing_mqtt(R"({"infrastructure": {}})");
        EXPECT_THROW(load_config(missing_mqtt.path(), get_schema_path()), std::runtime_error);
    }

    // Invalid log level
    {
        TempFile invalid_level(config_with_log_level("invalid"));
        EXPECT_THROW(load_config(invalid_level.path(), get_schema_path()), std::runtime_error);
    }

    // Port out of range
    {
        TempFile port_too_low(config_with_port(1023));
        EXPECT_THROW(load_config(port_too_low.path(), get_schema_path()), std::runtime_error);
    }
    {
        TempFile port_too_high(config_with_port(65536));
        EXPECT_THROW(load_config(port_too_high.path(), get_schema_path()), std::runtime_error);
    }

    // Extra properties not allowed at root level
    {
        TempFile extra_property(R"({
            "infrastructure": {"mqtt": {"host": "localhost", "port": 1883, "insecure": true}},
            "extra": "value"
        })");
        EXPECT_THROW(load_config(extra_property.path(), get_schema_path()), std::runtime_error);
    }
}

TEST(ConfigLoaderTest, EnvValidationErrors) {
    TempFile config_file(MINIMAL_CONFIG);

    // Invalid log level
    {
        ScopedEnv env(tracker::env::LOG_LEVEL, "invalid_level");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }

    // Non-numeric port
    {
        ScopedEnv env(tracker::env::HEALTHCHECK_PORT, "not_a_number");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }

    // Port out of range (too low, too high, overflow)
    {
        ScopedEnv env(tracker::env::HEALTHCHECK_PORT, "1000");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }
    {
        ScopedEnv env(tracker::env::HEALTHCHECK_PORT, "70000");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }
    // Covers std::out_of_range (lines 96-97)
    {
        ScopedEnv env(tracker::env::HEALTHCHECK_PORT, "99999999999999999999");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }
}

} // namespace
} // namespace tracker
