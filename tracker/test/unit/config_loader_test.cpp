// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"
#include "scene_loader.hpp"

#include "env_vars.hpp"
#include "utils/scoped_env.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>
#include <optional>

namespace tracker {
namespace {

using test::ScopedEnv;

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
 * @brief RAII helper for creating temporary scene files.
 *
 * Creates file in temp directory for loading via scenes.file_path
 */
class TempSceneFile {
public:
    TempSceneFile(const std::string& content) {
        path_ = std::filesystem::temp_directory_path() /
                ("tracker_scene_test_" + std::to_string(counter_++) + ".json");
        std::ofstream ofs(path_);
        ofs << content;
    }

    ~TempSceneFile() { std::filesystem::remove(path_); }

    const std::filesystem::path& path() const { return path_; }
    std::string filename() const { return path_.filename().string(); }

private:
    std::filesystem::path path_;
    static inline int counter_ = 0;
};

/// Empty scenes file content (valid JSON array with no scenes)
constexpr char EMPTY_SCENES[] = "[]";

/// Global empty scenes file for tests (created once, reused)
class GlobalEmptyScenes {
public:
    static const std::filesystem::path& path() {
        static GlobalEmptyScenes instance;
        return instance.path_;
    }

private:
    GlobalEmptyScenes() {
        path_ = std::filesystem::temp_directory_path() / "tracker_test_empty_scenes.json";
        std::ofstream ofs(path_);
        ofs << EMPTY_SCENES;
    }
    ~GlobalEmptyScenes() { std::filesystem::remove(path_); }
    std::filesystem::path path_;
};

/**
 * @brief Get path to the schema file (production schema used in tests).
 */
std::filesystem::path get_schema_path() {
    const auto this_file = std::filesystem::weakly_canonical(std::filesystem::path(__FILE__));
    const auto project_root = this_file.parent_path().parent_path().parent_path();
    return project_root / "schema" / "config.schema.json";
}

/// Get path to empty scenes file
std::string empty_scenes_path() {
    return GlobalEmptyScenes::path().string();
}

// Valid configuration tests
//

/// Minimal valid config (uses global empty scenes file)
std::string MINIMAL_CONFIG() {
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      },
      "scenes": {
        "source": "file",
        "file_path": ")" +
           empty_scenes_path() + R"("
      }
    })";
}

// Helper to create config with file-based scenes (requires absolute path)
std::string minimal_config_with_scenes(const std::string& scene_file_path) {
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      },
      "scenes": {
        "source": "file",
        "file_path": ")" +
           scene_file_path + R"("
      }
    })";
}

// Helper to create config with observability.logging.level
std::string config_with_log_level(const std::string& level,
                                  const std::string& scene_file_path = "") {
    std::string path = scene_file_path.empty() ? empty_scenes_path() : scene_file_path;
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      },
      "scenes": {
        "source": "file",
        "file_path": ")" +
           path + R"("
      },
      "observability": {"logging": {"level": ")" +
           level + R"("}}
    })";
}

// Helper to create config with infrastructure.tracker.healthcheck.port
std::string config_with_port(int port, const std::string& scene_file_path = "") {
    std::string path = scene_file_path.empty() ? empty_scenes_path() : scene_file_path;
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true},
        "tracker": {"healthcheck": {"port": )" +
           std::to_string(port) + R"(}}
      },
      "scenes": {
        "source": "file",
        "file_path": ")" +
           path + R"("
      }
    })";
}

// Helper to create config with both log level and port
std::string config_with_level_and_port(const std::string& level, int port,
                                       const std::string& scene_file_path = "") {
    std::string path = scene_file_path.empty() ? empty_scenes_path() : scene_file_path;
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true},
        "tracker": {"healthcheck": {"port": )" +
           std::to_string(port) + R"(}}
      },
      "scenes": {
        "source": "file",
        "file_path": ")" +
           path + R"("
      },
      "observability": {"logging": {"level": ")" +
           level + R"("}}
    })";
}

TEST(ConfigLoaderTest, LoadValidConfig) {
    TempFile config_file(config_with_level_and_port("debug", 9000));

    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.observability.logging.level, "debug");
    EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 9000);
}

TEST(ConfigLoaderTest, LoadAllLogLevelsAndPortBoundaries) {
    // Test all log levels (schema uses "warning" not "warn")
    for (const auto& level : {"trace", "debug", "info", "warning", "error"}) {
        TempFile config_file(config_with_log_level(level));
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.observability.logging.level, level);
    }

    // Test port boundaries
    {
        TempFile config_file(config_with_port(1024));
        EXPECT_EQ(load_config(config_file.path(), get_schema_path())
                      .infrastructure.tracker.healthcheck.port,
                  1024);
    }
    {
        TempFile config_file(config_with_port(65535));
        EXPECT_EQ(load_config(config_file.path(), get_schema_path())
                      .infrastructure.tracker.healthcheck.port,
                  65535);
    }
}

TEST(ConfigLoaderTest, DefaultValues) {
    // Minimal config should use defaults: log_level="info", healthcheck_port=8080
    TempFile config_file(MINIMAL_CONFIG());
    auto config = load_config(config_file.path(), get_schema_path());
    EXPECT_EQ(config.observability.logging.level, "info");
    EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 8080);
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
    TempFile valid_config(MINIMAL_CONFIG());

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
        TempFile valid_config(MINIMAL_CONFIG());
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
    TempFile config_file(MINIMAL_CONFIG());

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
// Empty environment variable tests (should be treated as unset)
// This is important for CI environments that may export variables with empty values
//

TEST(ConfigLoaderTest, EmptyEnvVarsTreatedAsUnset) {
    TempFile config_file(config_with_level_and_port("debug", 9000));

    // Empty MQTT_PORT should fall back to config file value
    {
        ScopedEnv env(tracker::env::MQTT_PORT, "");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.infrastructure.mqtt.port, 1883); // From config file
    }

    // Empty HEALTHCHECK_PORT should fall back to config file value
    {
        ScopedEnv env(tracker::env::HEALTHCHECK_PORT, "");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.infrastructure.tracker.healthcheck.port, 9000); // From config file
    }

    // Empty LOG_LEVEL should fall back to config file value
    {
        ScopedEnv env(tracker::env::LOG_LEVEL, "");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.observability.logging.level, "debug"); // From config file
    }

    // Empty MQTT_HOST should fall back to config file value
    {
        ScopedEnv env(tracker::env::MQTT_HOST, "");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_EQ(config.infrastructure.mqtt.host, "localhost"); // From config file
    }

    // Empty MQTT_INSECURE should fall back to config file value
    {
        ScopedEnv env(tracker::env::MQTT_INSECURE, "");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_TRUE(config.infrastructure.mqtt.insecure); // From config file
    }
}

//
// TLS environment variable override tests (covers lines 252-265)
//

TEST(ConfigLoaderTest, TlsEnvOverrides_CreatesTlsConfigWhenNotInFile) {
    TempFile config_file(MINIMAL_CONFIG());

    // Setting TLS CA cert env should create TLS config
    {
        ScopedEnv env(tracker::env::MQTT_TLS_CA_CERT, "/path/to/ca.crt");
        auto config = load_config(config_file.path(), get_schema_path());
        ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
        EXPECT_EQ(config.infrastructure.mqtt.tls->ca_cert_path, "/path/to/ca.crt");
    }
}

TEST(ConfigLoaderTest, TlsEnvOverrides_AllTlsFields) {
    TempFile config_file(MINIMAL_CONFIG());

    ScopedEnv env_ca(tracker::env::MQTT_TLS_CA_CERT, "/path/to/ca.crt");
    ScopedEnv env_cert(tracker::env::MQTT_TLS_CLIENT_CERT, "/path/to/client.crt");
    ScopedEnv env_key(tracker::env::MQTT_TLS_CLIENT_KEY, "/path/to/client.key");
    ScopedEnv env_verify(tracker::env::MQTT_TLS_VERIFY_SERVER, "true");

    auto config = load_config(config_file.path(), get_schema_path());

    ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
    EXPECT_EQ(config.infrastructure.mqtt.tls->ca_cert_path, "/path/to/ca.crt");
    EXPECT_EQ(config.infrastructure.mqtt.tls->client_cert_path, "/path/to/client.crt");
    EXPECT_EQ(config.infrastructure.mqtt.tls->client_key_path, "/path/to/client.key");
    EXPECT_TRUE(config.infrastructure.mqtt.tls->verify_server);
}

TEST(ConfigLoaderTest, TlsEnvOverrides_VerifyServerFalse) {
    TempFile config_file(MINIMAL_CONFIG());

    ScopedEnv env_verify(tracker::env::MQTT_TLS_VERIFY_SERVER, "false");
    auto config = load_config(config_file.path(), get_schema_path());

    ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
    EXPECT_FALSE(config.infrastructure.mqtt.tls->verify_server);
}

TEST(ConfigLoaderTest, TlsEnvOverrides_VerifyServerVariants) {
    TempFile config_file(MINIMAL_CONFIG());

    // Test "1" = true
    {
        ScopedEnv env(tracker::env::MQTT_TLS_VERIFY_SERVER, "1");
        auto config = load_config(config_file.path(), get_schema_path());
        ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
        EXPECT_TRUE(config.infrastructure.mqtt.tls->verify_server);
    }

    // Test "0" = false
    {
        ScopedEnv env(tracker::env::MQTT_TLS_VERIFY_SERVER, "0");
        auto config = load_config(config_file.path(), get_schema_path());
        ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
        EXPECT_FALSE(config.infrastructure.mqtt.tls->verify_server);
    }

    // Test "yes" = true
    {
        ScopedEnv env(tracker::env::MQTT_TLS_VERIFY_SERVER, "yes");
        auto config = load_config(config_file.path(), get_schema_path());
        ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
        EXPECT_TRUE(config.infrastructure.mqtt.tls->verify_server);
    }

    // Test "no" = false
    {
        ScopedEnv env(tracker::env::MQTT_TLS_VERIFY_SERVER, "no");
        auto config = load_config(config_file.path(), get_schema_path());
        ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
        EXPECT_FALSE(config.infrastructure.mqtt.tls->verify_server);
    }
}

TEST(ConfigLoaderTest, TlsEnvOverrides_InvalidBoolThrows) {
    TempFile config_file(MINIMAL_CONFIG());

    ScopedEnv env(tracker::env::MQTT_TLS_VERIFY_SERVER, "invalid_bool");
    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, MqttHostEnvOverride) {
    TempFile config_file(MINIMAL_CONFIG());

    ScopedEnv env(tracker::env::MQTT_HOST, "broker.example.com");
    auto config = load_config(config_file.path(), get_schema_path());
    EXPECT_EQ(config.infrastructure.mqtt.host, "broker.example.com");
}

TEST(ConfigLoaderTest, MqttPortEnvOverride) {
    TempFile config_file(MINIMAL_CONFIG());

    ScopedEnv env(tracker::env::MQTT_PORT, "8883");
    auto config = load_config(config_file.path(), get_schema_path());
    EXPECT_EQ(config.infrastructure.mqtt.port, 8883);
}

TEST(ConfigLoaderTest, SchemaValidationEnvOverride) {
    TempFile config_file(MINIMAL_CONFIG());

    // Test disabling schema validation
    {
        ScopedEnv env(tracker::env::MQTT_SCHEMA_VALIDATION, "false");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_FALSE(config.infrastructure.tracker.schema_validation);
    }

    // Test enabling schema validation
    {
        ScopedEnv env(tracker::env::MQTT_SCHEMA_VALIDATION, "true");
        auto config = load_config(config_file.path(), get_schema_path());
        EXPECT_TRUE(config.infrastructure.tracker.schema_validation);
    }
}

//
// TLS config from JSON file tests (covers lines 193-210)
//

// Helper to create config with TLS settings in JSON
std::string config_with_tls(const std::string& ca_cert = "", const std::string& client_cert = "",
                            const std::string& client_key = "", bool verify_server = true) {
    std::string tls_block = R"("tls": {)";
    std::vector<std::string> fields;

    if (!ca_cert.empty()) {
        fields.push_back(R"("ca_cert_path": ")" + ca_cert + R"(")");
    }
    if (!client_cert.empty()) {
        fields.push_back(R"("client_cert_path": ")" + client_cert + R"(")");
    }
    if (!client_key.empty()) {
        fields.push_back(R"("client_key_path": ")" + client_key + R"(")");
    }
    fields.push_back(std::string(R"("verify_server": )") + (verify_server ? "true" : "false"));

    for (size_t i = 0; i < fields.size(); ++i) {
        tls_block += fields[i];
        if (i < fields.size() - 1)
            tls_block += ", ";
    }
    tls_block += "}";

    return R"({
      "infrastructure": {
        "mqtt": {
          "host": "localhost",
          "port": 8883,
          "insecure": false,
          )" +
           tls_block +
           R"(
        }
      },
      "scenes": {
        "source": "file",
        "file_path": ")" +
           empty_scenes_path() + R"("
      }
    })";
}

TEST(ConfigLoaderTest, TlsConfigFromJsonFile) {
    TempFile config_file(
        config_with_tls("/path/to/ca.crt", "/path/to/client.crt", "/path/to/client.key", true));

    auto config = load_config(config_file.path(), get_schema_path());

    ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
    EXPECT_EQ(config.infrastructure.mqtt.tls->ca_cert_path, "/path/to/ca.crt");
    EXPECT_EQ(config.infrastructure.mqtt.tls->client_cert_path, "/path/to/client.crt");
    EXPECT_EQ(config.infrastructure.mqtt.tls->client_key_path, "/path/to/client.key");
    EXPECT_TRUE(config.infrastructure.mqtt.tls->verify_server);
}

TEST(ConfigLoaderTest, TlsConfigFromJsonFile_VerifyServerFalse) {
    TempFile config_file(config_with_tls("/path/to/ca.crt", "", "", false));

    auto config = load_config(config_file.path(), get_schema_path());

    ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
    EXPECT_FALSE(config.infrastructure.mqtt.tls->verify_server);
}

TEST(ConfigLoaderTest, TlsConfigFromJsonFile_PartialConfig) {
    // Only CA cert specified
    TempFile config_file(config_with_tls("/path/to/ca.crt"));

    auto config = load_config(config_file.path(), get_schema_path());

    ASSERT_TRUE(config.infrastructure.mqtt.tls.has_value());
    EXPECT_EQ(config.infrastructure.mqtt.tls->ca_cert_path, "/path/to/ca.crt");
    EXPECT_TRUE(config.infrastructure.mqtt.tls->client_cert_path.empty());
    EXPECT_TRUE(config.infrastructure.mqtt.tls->client_key_path.empty());
}

//
// Tests for missing required fields (covers lines 176-177, 183-184)
// These require a permissive schema that doesn't enforce host/port
//

TEST(ConfigLoaderTest, MissingMqttHostThrows) {
    // Config with port but no host - use a permissive schema
    const char* config_no_host = R"({
      "infrastructure": {
        "mqtt": {"port": 1883, "insecure": true}
      }
    })";

    // Create a permissive schema that doesn't require host/port
    const char* permissive_schema = R"({
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "object"
    })";

    TempFile config_file(config_no_host);
    TempFile schema_file(permissive_schema);

    EXPECT_THROW(load_config(config_file.path(), schema_file.path()), std::runtime_error);
}

TEST(ConfigLoaderTest, MissingMqttPortThrows) {
    // Config with host but no port - use a permissive schema
    const char* config_no_port = R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "insecure": true}
      }
    })";

    // Create a permissive schema that doesn't require host/port
    const char* permissive_schema = R"({
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "object"
    })";

    TempFile config_file(config_no_port);
    TempFile schema_file(permissive_schema);

    EXPECT_THROW(load_config(config_file.path(), schema_file.path()), std::runtime_error);
}

//
// Scene configuration tests (file-based loading)
//

// Helper to create config with file-based scenes (file path must be absolute for temp files)
std::string config_with_scene_file(const std::string& scene_file_path) {
    return R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      },
      "scenes": {
        "source": "file",
        "file_path": ")" +
           scene_file_path + R"("
      }
    })";
}

TEST(ConfigLoaderTest, LoadFileScenes) {
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "Test Scene",
        "cameras": [
          {
            "uid": "cam-001",
            "name": "Camera 1",
            "intrinsics": {
              "fx": 905.0, "fy": 905.0, "cx": 640.0, "cy": 360.0,
              "distortion": {"k1": 0.1, "k2": 0.2, "p1": 0.01, "p2": 0.02}
            },
            "extrinsics": {
              "translation": [1.5, 2.5, 3.0],
              "rotation": [-135.0, 10.0, 20.0],
              "scale": [1.0, 1.0, 1.0]
            }
          }
        ]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    EXPECT_EQ(config.scenes.source, SceneSource::File);
    ASSERT_TRUE(config.scenes.file_path.has_value());
    EXPECT_EQ(*config.scenes.file_path, scene_file.path().string());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    auto scenes_data = scene_loader->load();

    ASSERT_EQ(scenes_data.size(), 1);
    EXPECT_EQ(scenes_data[0].uid, "scene-001");
    EXPECT_EQ(scenes_data[0].name, "Test Scene");
    ASSERT_EQ(scenes_data[0].cameras.size(), 1);

    const auto& cam = scenes_data[0].cameras[0];
    EXPECT_EQ(cam.uid, "cam-001");
    EXPECT_EQ(cam.name, "Camera 1");
    EXPECT_DOUBLE_EQ(cam.intrinsics.fx, 905.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.fy, 905.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.cx, 640.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.cy, 360.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.k1, 0.1);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.k2, 0.2);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.p1, 0.01);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.p2, 0.02);
    // Extrinsics - camera pose in world coordinates
    EXPECT_DOUBLE_EQ(cam.extrinsics.translation[0], 1.5);
    EXPECT_DOUBLE_EQ(cam.extrinsics.translation[1], 2.5);
    EXPECT_DOUBLE_EQ(cam.extrinsics.translation[2], 3.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.rotation[0], -135.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.rotation[1], 10.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.rotation[2], 20.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.scale[0], 1.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.scale[1], 1.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.scale[2], 1.0);
}

TEST(ConfigLoaderTest, LoadMultipleScenes) {
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "Queuing",
        "cameras": [
          {"uid": "qcam1", "name": "QCam 1", "intrinsics": {}, "extrinsics": {"translation": [1.0, 2.0, 3.0], "rotation": [-135.0, 10.0, 20.0], "scale": [1.0, 1.0, 1.0]}},
          {"uid": "qcam2", "name": "QCam 2", "intrinsics": {}, "extrinsics": {"translation": [4.0, 5.0, 6.0], "rotation": [-140.0, 15.0, 25.0], "scale": [1.0, 1.0, 1.0]}}
        ]
      },
      {
        "uid": "scene-002",
        "name": "Retail",
        "cameras": [
          {"uid": "rcam1", "name": "RCam 1", "intrinsics": {}, "extrinsics": {"translation": [2.5, 1.0, 2.5], "rotation": [-130.0, -10.0, -15.0], "scale": [1.0, 1.0, 1.0]}}
        ]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    auto scenes_data = scene_loader->load();

    ASSERT_EQ(scenes_data.size(), 2);
    EXPECT_EQ(scenes_data[0].name, "Queuing");
    EXPECT_EQ(scenes_data[0].cameras.size(), 2);
    EXPECT_EQ(scenes_data[1].name, "Retail");
    EXPECT_EQ(scenes_data[1].cameras.size(), 1);
}

TEST(ConfigLoaderTest, ScenesOmittedThrows) {
    // When scenes section is omitted, schema validation should fail
    const char* config = R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      }
    })";
    TempFile config_file(config);
    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, FileScenesWithoutFilePathThrows) {
    const char* config = R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      },
      "scenes": {
        "source": "file"
      }
    })";

    TempFile config_file(config);
    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, FileScenesFileNotFoundThrows) {
    TempFile config_file(config_with_scene_file("/nonexistent/path/to/scenes.json"));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, FileScenesInvalidJsonThrows) {
    TempSceneFile scene_file("{ invalid json }");
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, FileScenesNotArrayThrows) {
    TempSceneFile scene_file(R"({"not": "an array"})");
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, InvalidScenesSourceThrows) {
    const char* config = R"({
      "infrastructure": {
        "mqtt": {"host": "localhost", "port": 1883, "insecure": true}
      },
      "scenes": {
        "source": "invalid"
      }
    })";

    TempFile config_file(config);
    EXPECT_THROW(load_config(config_file.path(), get_schema_path()), std::runtime_error);
}

TEST(ConfigLoaderTest, SceneMissingUidThrows) {
    const char* scenes = R"([
      {
        "name": "Missing UID",
        "cameras": [{"uid": "cam-001", "name": "Camera", "intrinsics": {}, "extrinsics": {"translation": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]}}]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, SceneMissingNameThrows) {
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "cameras": [{"uid": "cam-001", "name": "Camera", "intrinsics": {}, "extrinsics": {"translation": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]}}]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, SceneMissingCamerasThrows) {
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "No Cameras"
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, CameraMissingUidThrows) {
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "Test Scene",
        "cameras": [{"name": "Missing UID Camera", "intrinsics": {}, "extrinsics": {"translation": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]}}]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, CameraMissingNameThrows) {
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "Test Scene",
        "cameras": [{"uid": "cam-001", "intrinsics": {}, "extrinsics": {"translation": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]}}]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, CameraMissingExtrinsicsThrows) {
    // Camera without extrinsics should throw (extrinsics are required)
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "Test Scene",
        "cameras": [{"uid": "cam-001", "name": "Basic Camera", "intrinsics": {}}]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, CameraOptionalIntrinsicsDistortionDefaults) {
    // Camera without intrinsics/distortion values should use defaults, but extrinsics required
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "Test Scene",
        "cameras": [{
          "uid": "cam-001",
          "name": "Basic Camera",
          "intrinsics": {},
          "extrinsics": {
            "translation": [1.0, 2.0, 3.0],
            "rotation": [-135.0, 10.0, 20.0],
            "scale": [1.0, 1.0, 1.0]
          }
        }]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    auto scenes_data = scene_loader->load();

    const auto& cam = scenes_data[0].cameras[0];
    // Intrinsics/distortion default to 0.0
    EXPECT_DOUBLE_EQ(cam.intrinsics.fx, 0.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.fy, 0.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.cx, 0.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.cy, 0.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.k1, 0.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.k2, 0.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.p1, 0.0);
    EXPECT_DOUBLE_EQ(cam.intrinsics.distortion.p2, 0.0);
    // Extrinsics are parsed
    EXPECT_DOUBLE_EQ(cam.extrinsics.translation[0], 1.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.rotation[0], -135.0);
    EXPECT_DOUBLE_EQ(cam.extrinsics.scale[0], 1.0);
}

TEST(ConfigLoaderTest, SceneNotObjectThrows) {
    // Scene array contains non-object element
    const char* scenes = R"(["not-an-object", 123, null])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

TEST(ConfigLoaderTest, CameraNotObjectThrows) {
    // Camera array contains non-object element
    const char* scenes = R"([
      {
        "uid": "scene-001",
        "name": "Test Scene",
        "cameras": ["not-an-object", 123]
      }
    ])";

    TempSceneFile scene_file(scenes);
    TempFile config_file(config_with_scene_file(scene_file.path().string()));
    auto config = load_config(config_file.path(), get_schema_path());

    auto scene_loader = create_scene_loader(config.scenes, config_file.path().parent_path());
    EXPECT_THROW(scene_loader->load(), std::runtime_error);
}

} // namespace
} // namespace tracker
