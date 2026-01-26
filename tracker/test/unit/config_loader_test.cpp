// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"

#include "env_vars.hpp"

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

/**
 * @brief Create a valid config JSON string with optional overrides.
 */
std::string make_config(const std::string& log_level = "info", int healthcheck_port = 8080,
                        const std::string& mqtt_host = "localhost", int mqtt_port = 1883) {
    return R"({"infrastructure": {"mqtt": {"host": ")" + mqtt_host + R"(", "port": )" +
           std::to_string(mqtt_port) +
           R"(, "insecure": true}, "tracker": {"healthcheck": {"port": )" +
           std::to_string(healthcheck_port) + R"(}}}, "observability": {"logging": {"level": ")" +
           log_level + R"("}}})";
}

//
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
    TempFile config_file(make_config("debug", 9000));

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.observability.logging.level, "debug");
    EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 9000);
    EXPECT_EQ(config.infrastructure.mqtt.host, "localhost");
    EXPECT_EQ(config.infrastructure.mqtt.port, 1883);
}

TEST(ConfigLoaderTest, LoadAllLogLevelsAndPortBoundaries) {
    // Test all log levels (schema uses "warning" not "warn")
    for (const auto& level : {"trace", "debug", "info", "warning", "error"}) {
        TempFile config_file(make_config(level, 8080));
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.observability.logging.level, level);
    }

    // Test port boundaries
    {
        TempFile config_file(make_config("info", 1024));
        EXPECT_EQ(load_config(config_file.path(), get_schema_path())
                      .infrastructure.tracker.healthcheck.port,
                  1024);
    }
    {
        TempFile config_file(make_config("info", 65535));
        EXPECT_EQ(load_config(config_file.path(), get_schema_path())
                      .infrastructure.tracker.healthcheck.port,
                  65535);
    }
}

TEST(ConfigLoaderTest, DefaultValues) {
    // Minimal config should use defaults: log_level="info", healthcheck_port=8080
    TempFile config_file(MINIMAL_CONFIG);
    auto config = load_config(config_file.path(), get_schema_path());
    EXPECT_EQ(config.observability.logging.level, "info");
    EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 8080);
}

//
// Environment variable override tests
//

TEST(ConfigLoaderTest, EnvOverrides) {
    TempFile config_file(make_config("info", 8080));

    // Override log level only
    {
        ScopedEnv env(tracker::env::LOG_LEVEL, "trace");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.observability.logging.level, "trace");
        EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 8080);
    }

    // Override port only
    {
        ScopedEnv env(tracker::env::HEALTHCHECK_PORT, "9999");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.observability.logging.level, "info");
        EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 9999);
    }

    // Override both
    {
        ScopedEnv env_level(tracker::env::LOG_LEVEL, "error");
        ScopedEnv env_port(tracker::env::HEALTHCHECK_PORT, "5000");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.observability.logging.level, "error");
        EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 5000);
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
    // Missing required infrastructure section
    EXPECT_THROW(load_config(TempFile(R"({})").path(), get_schema_path()), std::runtime_error);

    // Missing required mqtt section
    EXPECT_THROW(load_config(TempFile(R"({"infrastructure": {}})").path(), get_schema_path()),
                 std::runtime_error);

    // Missing required mqtt.host
    EXPECT_THROW(load_config(TempFile(R"({"infrastructure": {"mqtt": {"port": 1883}}})").path(),
                             get_schema_path()),
                 std::runtime_error);

    // Missing required mqtt.port
    EXPECT_THROW(
        load_config(TempFile(R"({"infrastructure": {"mqtt": {"host": "localhost"}}})").path(),
                    get_schema_path()),
        std::runtime_error);

    // Invalid log level
    EXPECT_THROW(
        load_config(
            TempFile(
                R"({"infrastructure": {"mqtt": {"host": "localhost", "port": 1883}}, "observability": {"logging": {"level": "invalid"}}})")
                .path(),
            get_schema_path()),
        std::runtime_error);

    // Healthcheck port out of range
    EXPECT_THROW(
        load_config(
            TempFile(
                R"({"infrastructure": {"mqtt": {"host": "localhost", "port": 1883}, "tracker": {"healthcheck": {"port": 1023}}}})")
                .path(),
            get_schema_path()),
        std::runtime_error);
    EXPECT_THROW(
        load_config(
            TempFile(
                R"({"infrastructure": {"mqtt": {"host": "localhost", "port": 1883}, "tracker": {"healthcheck": {"port": 65536}}}})")
                .path(),
            get_schema_path()),
        std::runtime_error);

    // Extra properties not allowed at root
    EXPECT_THROW(
        load_config(
            TempFile(
                R"({"infrastructure": {"mqtt": {"host": "localhost", "port": 1883}}, "extra": "value"})")
                .path(),
            get_schema_path()),
        std::runtime_error);
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

//
// MQTT environment variable override tests
//

TEST(ConfigLoaderTest, MqttHostEnvOverride) {
    TempFile config_file(MINIMAL_CONFIG);

    ScopedEnv env(tracker::env::MQTT_HOST, "broker.example.com");
    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.infrastructure.mqtt.host, "broker.example.com");
}

TEST(ConfigLoaderTest, MqttPortEnvOverride) {
    TempFile config_file(MINIMAL_CONFIG);

    ScopedEnv env(tracker::env::MQTT_PORT, "8883");
    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.infrastructure.mqtt.port, 8883);
}

TEST(ConfigLoaderTest, MqttPortEnvOverrideAllowsLowPorts) {
    TempFile config_file(MINIMAL_CONFIG);

    // MQTT port allows 1-65535 (unlike healthcheck which requires 1024+)
    ScopedEnv env(tracker::env::MQTT_PORT, "22");
    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.infrastructure.mqtt.port, 22);
}

TEST(ConfigLoaderTest, MqttPortEnvValidationErrors) {
    TempFile config_file(MINIMAL_CONFIG);

    // Non-numeric
    {
        ScopedEnv env(tracker::env::MQTT_PORT, "not_a_port");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }

    // Zero (out of range)
    {
        ScopedEnv env(tracker::env::MQTT_PORT, "0");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }

    // Too high
    {
        ScopedEnv env(tracker::env::MQTT_PORT, "65536");
        EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
    }
}

TEST(ConfigLoaderTest, MqttInsecureEnvOverride) {
    TempFile config_file(MINIMAL_CONFIG);

    // Test various boolean representations
    {
        ScopedEnv env(tracker::env::MQTT_INSECURE, "false");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_FALSE(config.infrastructure.mqtt.insecure);
    }
    {
        ScopedEnv env(tracker::env::MQTT_INSECURE, "0");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_FALSE(config.infrastructure.mqtt.insecure);
    }
    {
        ScopedEnv env(tracker::env::MQTT_INSECURE, "no");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_FALSE(config.infrastructure.mqtt.insecure);
    }
    {
        ScopedEnv env(tracker::env::MQTT_INSECURE, "true");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_TRUE(config.infrastructure.mqtt.insecure);
    }
    {
        ScopedEnv env(tracker::env::MQTT_INSECURE, "1");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_TRUE(config.infrastructure.mqtt.insecure);
    }
    {
        ScopedEnv env(tracker::env::MQTT_INSECURE, "yes");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_TRUE(config.infrastructure.mqtt.insecure);
    }
}

TEST(ConfigLoaderTest, MqttInsecureEnvValidationError) {
    TempFile config_file(MINIMAL_CONFIG);

    ScopedEnv env(tracker::env::MQTT_INSECURE, "maybe");
    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

//
// TLS environment variable override tests
//

TEST(ConfigLoaderTest, TlsEnvOverridesCreateTlsConfig) {
    TempFile config_file(MINIMAL_CONFIG);

    // Setting any TLS env var should create the tls config
    ScopedEnv env(tracker::env::MQTT_TLS_CA_CERT, "/path/to/ca.pem");
    auto config = load_config(config_file.path(), get_schema_path());

    ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
    EXPECT_EQ(config.infrastructure.mqtt.tls->ca_cert_path, "/path/to/ca.pem");
}

TEST(ConfigLoaderTest, TlsEnvOverridesAllFields) {
    TempFile config_file(MINIMAL_CONFIG);

    ScopedEnv env_ca(tracker::env::MQTT_TLS_CA_CERT, "/certs/ca.pem");
    ScopedEnv env_cert(tracker::env::MQTT_TLS_CLIENT_CERT, "/certs/client.pem");
    ScopedEnv env_key(tracker::env::MQTT_TLS_CLIENT_KEY, "/certs/client.key");
    ScopedEnv env_verify(tracker::env::MQTT_TLS_VERIFY_SERVER, "false");

    auto config = load_config(config_file.path(), get_schema_path());

    ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
    EXPECT_EQ(config.infrastructure.mqtt.tls->ca_cert_path, "/certs/ca.pem");
    EXPECT_EQ(config.infrastructure.mqtt.tls->client_cert_path, "/certs/client.pem");
    EXPECT_EQ(config.infrastructure.mqtt.tls->client_key_path, "/certs/client.key");
    EXPECT_FALSE(config.infrastructure.mqtt.tls->verify_server);
}

TEST(ConfigLoaderTest, TlsVerifyServerEnvValidationError) {
    TempFile config_file(MINIMAL_CONFIG);

    ScopedEnv env(tracker::env::MQTT_TLS_VERIFY_SERVER, "invalid");
    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

} // namespace
} // namespace tracker
