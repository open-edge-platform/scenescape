// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"

#include "env_vars.hpp"

#include <cstdlib>
#include <fstream>
#include <optional>
#include <stdexcept>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/pointer.h>
#include <rapidjson/schema.h>
#include <rapidjson/stringbuffer.h>

namespace tracker {

namespace {

/**
 * @brief Load and parse JSON schema from file.
 */
rapidjson::SchemaDocument load_schema(const std::filesystem::path& schema_path) {
    std::ifstream ifs(schema_path);
    if (!ifs.is_open()) {
        throw std::runtime_error("Failed to open schema file: " + schema_path.string());
    }

    rapidjson::IStreamWrapper isw(ifs);
    rapidjson::Document schema_doc;
    schema_doc.ParseStream(isw);

    if (schema_doc.HasParseError()) {
        throw std::runtime_error("Failed to parse JSON schema: " + schema_path.string() +
                                 " at offset " + std::to_string(schema_doc.GetErrorOffset()));
    }

    return rapidjson::SchemaDocument(schema_doc);
}

/**
 * @brief Validate JSON document against schema.
 */
void validate_against_schema(const rapidjson::Document& doc,
                             const rapidjson::SchemaDocument& schema,
                             const std::filesystem::path& config_path) {
    rapidjson::SchemaValidator validator(schema);
    if (!doc.Accept(validator)) {
        rapidjson::StringBuffer sb;
        validator.GetInvalidSchemaPointer().StringifyUriFragment(sb);
        throw std::runtime_error("Config validation failed for " + config_path.string() +
                                 " at: " + sb.GetString() +
                                 ", keyword: " + validator.GetInvalidSchemaKeyword());
    }
}

/**
 * @brief Get optional environment variable value.
 * @note Empty strings are treated as unset
 */
std::optional<std::string> get_env(const char* name) {
    const char* value = std::getenv(name);
    if (value != nullptr && value[0] != '\0') {
        return std::string(value);
    }
    return std::nullopt;
}

/**
 * @brief Parse and validate log level from string.
 * @throws std::runtime_error if invalid log level
 */
std::string parse_log_level(const std::string& level, const std::string& source) {
    if (level == "trace" || level == "debug" || level == "info" || level == "warn" ||
        level == "error") {
        return level;
    }
    throw std::runtime_error("Invalid " + source + ": " + level +
                             " (must be trace|debug|info|warn|error)");
}

/**
 * @brief Parse and validate port number from string with configurable range.
 * @param port_str The port string to parse
 * @param source Source name for error messages
 * @param min_port Minimum valid port (inclusive)
 * @param max_port Maximum valid port (inclusive)
 * @throws std::runtime_error if invalid or out of range
 */
int parse_port(const std::string& port_str, const std::string& source, int min_port = 1,
               int max_port = 65535) {
    try {
        int port = std::stoi(port_str);
        if (port < min_port || port > max_port) {
            throw std::runtime_error(source + " out of range: " + port_str + " (must be " +
                                     std::to_string(min_port) + "-" + std::to_string(max_port) +
                                     ")");
        }
        return port;
    } catch (const std::invalid_argument&) {
        throw std::runtime_error("Invalid " + source + ": " + port_str);
    } catch (const std::out_of_range&) {
        throw std::runtime_error(source + " out of range: " + port_str);
    }
}

/**
 * @brief Parse and validate boolean from string.
 * @throws std::runtime_error if invalid boolean value
 */
bool parse_bool(const std::string& value, const std::string& source) {
    if (value == "true" || value == "1" || value == "yes") {
        return true;
    }
    if (value == "false" || value == "0" || value == "no") {
        return false;
    }
    throw std::runtime_error("Invalid " + source + ": " + value +
                             " (must be true/false, 1/0, or yes/no)");
}

/**
 * @brief Apply environment variable override to a field if the env var is set.
 * @tparam T Field type
 * @tparam Parser Callable that takes (string value, string source) and returns T
 */
template <typename T, typename Parser>
void apply_env(T& field, const char* env_name, Parser parser) {
    if (auto val = get_env(env_name); val.has_value()) {
        field = parser(val.value(), env_name);
    }
}

/// Overload for string fields (no parsing needed)
void apply_env_string(std::string& field, const char* env_name) {
    if (auto val = get_env(env_name); val.has_value()) {
        field = val.value();
    }
}

/**
 * @brief Get optional value from JSON using pointer path.
 * @tparam T Expected value type (std::string or double)
 * @param val The JSON value to query
 * @param pointer JSON pointer path (e.g., "/intrinsics/fx")
 * @return Optional containing value if found and correct type, nullopt otherwise
 */
template <typename T>
std::optional<T> get_value(const rapidjson::Value& val, const char* pointer) {
    rapidjson::Pointer ptr(pointer);
    if (auto* v = ptr.Get(val)) {
        if constexpr (std::is_same_v<T, std::string>) {
            if (v->IsString())
                return std::string(v->GetString());
        } else if constexpr (std::is_same_v<T, double>) {
            if (v->IsNumber())
                return v->GetDouble();
        }
    }
    return std::nullopt;
}

/**
 * @brief Get required value from JSON using pointer path.
 * @tparam T Expected value type (std::string)
 * @param val The JSON value to query
 * @param pointer JSON pointer path (e.g., "/uid")
 * @param context Context string for error messages (e.g., "scene", "camera")
 * @return Value if found and correct type
 * @throws std::runtime_error if value missing or wrong type
 */
template <typename T>
T require_value(const rapidjson::Value& val, const char* pointer, const char* context) {
    auto result = get_value<T>(val, pointer);
    if (!result.has_value()) {
        throw std::runtime_error(std::string(context) + " missing required '" + (pointer + 1) +
                                 "' field");
    }
    return result.value();
}

/**
 * @brief Get required array from JSON using pointer path.
 * @param val The JSON value to query
 * @param pointer JSON pointer path (e.g., "/cameras")
 * @param context Context string for error messages
 * @return Reference to the array
 * @throws std::runtime_error if value missing or not an array
 */
const rapidjson::Value::ConstArray require_array(const rapidjson::Value& val, const char* pointer,
                                                 const char* context) {
    rapidjson::Pointer ptr(pointer);
    if (auto* v = ptr.Get(val)) {
        if (v->IsArray()) {
            return v->GetArray();
        }
    }
    throw std::runtime_error(std::string(context) + " missing required '" + (pointer + 1) +
                             "' field");
}

/**
 * @brief Parse required array of 3 doubles from JSON.
 * @param val The JSON value to query
 * @param pointer JSON pointer path (e.g., "/translation")
 * @param context Context string for error messages (e.g., "camera 'camera1'")
 * @return std::array<double, 3> with parsed values
 * @throws std::runtime_error if array missing, wrong size, or contains non-numbers
 */
std::array<double, 3> require_array3(const rapidjson::Value& val, const char* pointer,
                                     const std::string& context) {
    rapidjson::Pointer ptr(pointer);
    auto* arr_val = ptr.Get(val);
    if (!arr_val || !arr_val->IsArray()) {
        throw std::runtime_error(context + " missing required '" + (pointer + 1) + "' field");
    }
    auto arr = arr_val->GetArray();
    if (arr.Size() != 3) {
        throw std::runtime_error(context + " '" + (pointer + 1) + "' must have exactly 3 elements");
    }
    std::array<double, 3> result;
    for (rapidjson::SizeType i = 0; i < 3; ++i) {
        if (!arr[i].IsNumber()) {
            throw std::runtime_error(context + " '" + (pointer + 1) + "' element " +
                                     std::to_string(i) + " is not a number");
        }
        result[i] = arr[i].GetDouble();
    }
    return result;
}

} // namespace

ServiceConfig load_config(const std::filesystem::path& config_path,
                          const std::filesystem::path& schema_path) {
    // Load and parse config file
    std::ifstream config_ifs(config_path);
    if (!config_ifs.is_open()) {
        throw std::runtime_error("Failed to open config file: " + config_path.string());
    }

    rapidjson::IStreamWrapper config_isw(config_ifs);
    rapidjson::Document config_doc;
    config_doc.ParseStream(config_isw);

    if (config_doc.HasParseError()) {
        throw std::runtime_error("Failed to parse config JSON: " + config_path.string() +
                                 " at offset " + std::to_string(config_doc.GetErrorOffset()));
    }

    // Load schema and validate
    auto schema = load_schema(schema_path);
    validate_against_schema(config_doc, schema, config_path);

    // Extract values from JSON with defaults using JSON Pointers (RFC6901)
    using rapidjson::GetValueByPointer;
    using rapidjson::GetValueByPointerWithDefault;

    ServiceConfig config;

    // Infrastructure - MQTT (required)
    if (auto* host = GetValueByPointer(config_doc, json::INFRASTRUCTURE_MQTT_HOST)) {
        config.infrastructure.mqtt.host = host->GetString();
    } else {
        throw std::runtime_error("Missing required config: " +
                                 std::string(json::INFRASTRUCTURE_MQTT_HOST));
    }

    if (auto* port = GetValueByPointer(config_doc, json::INFRASTRUCTURE_MQTT_PORT)) {
        config.infrastructure.mqtt.port = port->GetInt();
    } else {
        throw std::runtime_error("Missing required config: " +
                                 std::string(json::INFRASTRUCTURE_MQTT_PORT));
    }

    config.infrastructure.mqtt.insecure =
        GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_MQTT_INSECURE, false)
            .GetBool();

    // Infrastructure - MQTT TLS (optional)
    if (GetValueByPointer(config_doc, json::INFRASTRUCTURE_MQTT_TLS)) {
        TlsConfig tls_config;
        tls_config.ca_cert_path =
            GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_MQTT_TLS_CA_CERT_PATH, "")
                .GetString();
        tls_config.client_cert_path =
            GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_MQTT_TLS_CLIENT_CERT_PATH,
                                         "")
                .GetString();
        tls_config.client_key_path =
            GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_MQTT_TLS_CLIENT_KEY_PATH,
                                         "")
                .GetString();
        tls_config.verify_server =
            GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_MQTT_TLS_VERIFY_SERVER,
                                         true)
                .GetBool();
        config.infrastructure.mqtt.tls = tls_config;
    }

    // Infrastructure - Tracker Healthcheck (optional)
    config.infrastructure.tracker.healthcheck.port =
        GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_TRACKER_HEALTHCHECK_PORT,
                                     8080)
            .GetInt();

    // Infrastructure - Tracker Schema validation (optional, default true)
    config.infrastructure.tracker.schema_validation =
        GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_TRACKER_SCHEMA_VALIDATION,
                                     true)
            .GetBool();

    // Observability - Logging (optional)
    config.observability.logging.level =
        GetValueByPointerWithDefault(config_doc, json::OBSERVABILITY_LOGGING_LEVEL, "info")
            .GetString();

    // Scenes configuration (required)
    std::string source_str =
        GetValueByPointerWithDefault(config_doc, json::SCENES_SOURCE, "file").GetString();

    if (source_str == "file") {
        config.scenes.source = SceneSource::File;
    } else if (source_str == "api") {
        config.scenes.source = SceneSource::Api;
    } else {
        throw std::runtime_error("Invalid scenes.source: " + source_str +
                                 " (must be 'file' or 'api')");
    }

    if (config.scenes.source == SceneSource::File) {
        // Get file path and resolve relative to config directory
        if (auto* file_path_val = GetValueByPointer(config_doc, json::SCENES_FILE_PATH)) {
            config.scenes.file_path = std::string(file_path_val->GetString());
        } else {
            throw std::runtime_error("Missing required config: scenes.file_path (required when "
                                     "scenes.source='file')");
        }

        // Resolve relative path from config file directory
        std::filesystem::path scene_file_path(*config.scenes.file_path);
        if (!scene_file_path.is_absolute()) {
            scene_file_path = config_path.parent_path() / scene_file_path;
        }

        // Load and parse scene file
        std::ifstream scene_ifs(scene_file_path);
        if (!scene_ifs.is_open()) {
            throw std::runtime_error("Failed to open scene file: " + scene_file_path.string());
        }

        rapidjson::IStreamWrapper scene_isw(scene_ifs);
        rapidjson::Document scene_doc;
        scene_doc.ParseStream(scene_isw);

        if (scene_doc.HasParseError()) {
            throw std::runtime_error("Failed to parse scene JSON: " + scene_file_path.string() +
                                     " at offset " + std::to_string(scene_doc.GetErrorOffset()));
        }

        if (!scene_doc.IsArray()) {
            throw std::runtime_error("Scene file must contain a JSON array of scenes: " +
                                     scene_file_path.string());
        }

        // Parse scenes from file
        for (const auto& scene_val : scene_doc.GetArray()) {
            Scene scene;
            scene.uid = require_value<std::string>(scene_val, json::SCENE_UID, "scene");
            scene.name = require_value<std::string>(scene_val, json::SCENE_NAME, "scene");

            for (const auto& cam_val : require_array(scene_val, json::SCENE_CAMERAS, "scene")) {
                Camera camera;
                camera.uid = require_value<std::string>(cam_val, json::CAMERA_UID, "camera");
                camera.name = require_value<std::string>(cam_val, json::CAMERA_NAME, "camera");

                // Parse intrinsics (optional, default to 0.0)
                camera.intrinsics.fx =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_FX).value_or(0.0);
                camera.intrinsics.fy =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_FY).value_or(0.0);
                camera.intrinsics.cx =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_CX).value_or(0.0);
                camera.intrinsics.cy =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_CY).value_or(0.0);

                // Parse distortion (optional, default to 0.0) - nested under intrinsics
                camera.intrinsics.distortion.k1 =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_DISTORTION_K1).value_or(0.0);
                camera.intrinsics.distortion.k2 =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_DISTORTION_K2).value_or(0.0);
                camera.intrinsics.distortion.p1 =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_DISTORTION_P1).value_or(0.0);
                camera.intrinsics.distortion.p2 =
                    get_value<double>(cam_val, json::CAMERA_INTRINSICS_DISTORTION_P2).value_or(0.0);

                // Parse extrinsics (required - camera pose in world coordinates)
                // Reference: Python controller's CameraPose in
                // scene_common/src/scene_common/transform.py
                std::string cam_context = "camera '" + camera.uid + "'";
                camera.extrinsics.translation =
                    require_array3(cam_val, json::CAMERA_EXTRINSICS_TRANSLATION, cam_context);
                camera.extrinsics.rotation =
                    require_array3(cam_val, json::CAMERA_EXTRINSICS_ROTATION, cam_context);
                camera.extrinsics.scale =
                    require_array3(cam_val, json::CAMERA_EXTRINSICS_SCALE, cam_context);

                scene.cameras.push_back(std::move(camera));
            }

            config.scenes.data.push_back(std::move(scene));
        }
    }
    // Note: When scenes.source == "api", scenes are fetched from Manager REST API at runtime
    //       (not yet implemented - handled by the tracker runtime / scene management code).

    // Apply environment variable overrides
    apply_env(config.observability.logging.level, tracker::env::LOG_LEVEL, parse_log_level);
    apply_env(config.infrastructure.tracker.healthcheck.port, tracker::env::HEALTHCHECK_PORT,
              [](const std::string& v, const std::string& s) { return parse_port(v, s, 1024); });

    // MQTT overrides
    apply_env_string(config.infrastructure.mqtt.host, tracker::env::MQTT_HOST);
    apply_env(config.infrastructure.mqtt.port, tracker::env::MQTT_PORT,
              [](const std::string& v, const std::string& s) { return parse_port(v, s); });
    apply_env(config.infrastructure.mqtt.insecure, tracker::env::MQTT_INSECURE, parse_bool);

    // Tracker overrides
    apply_env(config.infrastructure.tracker.schema_validation, tracker::env::MQTT_SCHEMA_VALIDATION,
              parse_bool);

    // TLS overrides - create tls config if any TLS env var is set
    auto env_tls_ca = get_env(tracker::env::MQTT_TLS_CA_CERT);
    auto env_tls_cert = get_env(tracker::env::MQTT_TLS_CLIENT_CERT);
    auto env_tls_key = get_env(tracker::env::MQTT_TLS_CLIENT_KEY);
    auto env_tls_verify = get_env(tracker::env::MQTT_TLS_VERIFY_SERVER);

    if (env_tls_ca.has_value() || env_tls_cert.has_value() || env_tls_key.has_value() ||
        env_tls_verify.has_value()) {
        if (!config.infrastructure.mqtt.tls.has_value()) {
            config.infrastructure.mqtt.tls = TlsConfig{};
        }
        auto& tls = config.infrastructure.mqtt.tls.value();

        if (env_tls_ca.has_value())
            tls.ca_cert_path = env_tls_ca.value();
        if (env_tls_cert.has_value())
            tls.client_cert_path = env_tls_cert.value();
        if (env_tls_key.has_value())
            tls.client_key_path = env_tls_key.value();
        if (env_tls_verify.has_value())
            tls.verify_server =
                parse_bool(env_tls_verify.value(), tracker::env::MQTT_TLS_VERIFY_SERVER);
    }

    return config;
}

} // namespace tracker
