// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"

#include "env_vars.hpp"
#include "json_utils.hpp"

#include <cstdlib>
#include <fstream>
#include <stdexcept>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/pointer.h>
#include <rapidjson/schema.h>
#include <rapidjson/stringbuffer.h>

namespace tracker {

namespace {

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

/// @note Empty strings are treated as unset
std::optional<std::string> get_env(const char* name) {
    const char* value = std::getenv(name);
    if (value != nullptr && value[0] != '\0') {
        return std::string(value);
    }
    return std::nullopt;
}

/// @throws std::runtime_error if invalid log level
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

/// @throws std::runtime_error if invalid boolean value
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

    // Observability - Metrics (optional, schema enforces type + minimum)
    config.observability.metrics.enabled =
        GetValueByPointerWithDefault(config_doc, json::OBSERVABILITY_METRICS_ENABLED, false)
            .GetBool();
    config.observability.metrics.export_interval_s =
        GetValueByPointerWithDefault(config_doc, json::OBSERVABILITY_METRICS_EXPORT_INTERVAL_S, 60)
            .GetInt();

    // Observability - Tracing (optional, schema enforces type + minimum)
    config.observability.tracing.enabled =
        GetValueByPointerWithDefault(config_doc, json::OBSERVABILITY_TRACING_ENABLED, false)
            .GetBool();
    config.observability.tracing.export_interval_s =
        GetValueByPointerWithDefault(config_doc, json::OBSERVABILITY_TRACING_EXPORT_INTERVAL_S, 5)
            .GetInt();

    // Scenes configuration (required) - parse source and file_path only
    // Actual scene loading is done via ISceneLoader in main
    std::string source_str =
        GetValueByPointerWithDefault(config_doc, json::SCENES_SOURCE, "api").GetString();

    if (source_str == "file") {
        config.scenes.source = SceneSource::File;
    } else if (source_str == "api") {
        config.scenes.source = SceneSource::Api;
    } else {
        throw std::runtime_error("Invalid scenes.source: " + source_str +
                                 " (must be 'file' or 'api')");
    }

    if (config.scenes.source == SceneSource::File) {
        // Get file path (validation that file exists is done by ISceneLoader)
        if (auto* file_path_val = GetValueByPointer(config_doc, json::SCENES_FILE_PATH)) {
            config.scenes.file_path = std::string(file_path_val->GetString());
        } else {
            throw std::runtime_error("Missing required config: scenes.file_path (required when "
                                     "scenes.source='file')");
        }
    }

    // Infrastructure - Manager (required when scenes.source='api')
    if (GetValueByPointer(config_doc, json::INFRASTRUCTURE_MANAGER)) {
        ManagerConfig manager_config;
        if (auto* url = GetValueByPointer(config_doc, json::INFRASTRUCTURE_MANAGER_URL)) {
            manager_config.url = url->GetString();
        } else {
            throw std::runtime_error("Missing required config: " +
                                     std::string(json::INFRASTRUCTURE_MANAGER_URL));
        }
        if (auto* auth = GetValueByPointer(config_doc, json::INFRASTRUCTURE_MANAGER_AUTH_PATH)) {
            manager_config.auth_path = auth->GetString();
        } else {
            throw std::runtime_error("Missing required config: " +
                                     std::string(json::INFRASTRUCTURE_MANAGER_AUTH_PATH));
        }
        if (auto* ca = GetValueByPointer(config_doc, json::INFRASTRUCTURE_MANAGER_CA_CERT_PATH)) {
            manager_config.ca_cert_path = std::string(ca->GetString());
        }
        config.infrastructure.manager = manager_config;
    }

    // Infrastructure - OTLP (optional, required when metrics or tracing enabled)
    if (GetValueByPointer(config_doc, json::INFRASTRUCTURE_OTLP)) {
        OtlpConfig otlp_config;
        if (auto* endpoint = GetValueByPointer(config_doc, json::INFRASTRUCTURE_OTLP_ENDPOINT)) {
            otlp_config.endpoint = endpoint->GetString();
        } else {
            throw std::runtime_error("Missing required config: " +
                                     std::string(json::INFRASTRUCTURE_OTLP_ENDPOINT));
        }
        otlp_config.insecure =
            GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_OTLP_INSECURE, true)
                .GetBool();
        config.infrastructure.otlp = otlp_config;
    }

    // Tracking configuration (optional - defaults from constants in config_loader.hpp)
    config.tracking.max_lag_s =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_MAX_LAG_S, kDefaultMaxLagS)
            .GetDouble();
    config.tracking.time_chunking_rate_fps =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_TIME_CHUNKING_RATE_FPS,
                                     kDefaultTimeChunkingRateFps)
            .GetInt();
    config.tracking.max_workers =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_MAX_WORKERS, kDefaultMaxWorkers)
            .GetInt();
    config.tracking.max_unreliable_time_s =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_MAX_UNRELIABLE_TIME_S,
                                     kDefaultMaxUnreliableTimeS)
            .GetDouble();
    config.tracking.non_measurement_time_dynamic_s =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_NON_MEASUREMENT_TIME_DYNAMIC_S,
                                     kDefaultNonMeasurementTimeDynamicS)
            .GetDouble();
    config.tracking.non_measurement_time_static_s =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_NON_MEASUREMENT_TIME_STATIC_S,
                                     kDefaultNonMeasurementTimeStaticS)
            .GetDouble();

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

    // Tracking overrides
    apply_env(config.tracking.max_lag_s, tracker::env::MAX_LAG_S,
              [](const std::string& v, const std::string& s) {
                  try {
                      double val = std::stod(v);
                      if (val < 0) {
                          throw std::runtime_error(s + " must be >= 0: " + v);
                      }
                      return val;
                  } catch (const std::invalid_argument&) {
                      throw std::runtime_error("Invalid " + s + ": " + v);
                  }
              });
    apply_env(config.tracking.time_chunking_rate_fps, tracker::env::TIME_CHUNKING_RATE_FPS,
              [](const std::string& v, const std::string& s) {
                  try {
                      int val = std::stoi(v);
                      if (val < 1 || val > 60) {
                          throw std::runtime_error(s + " out of range: " + v + " (must be 1-60)");
                      }
                      return val;
                  } catch (const std::invalid_argument&) {
                      throw std::runtime_error("Invalid " + s + ": " + v);
                  }
              });
    apply_env(config.tracking.max_workers, tracker::env::MAX_WORKERS,
              [](const std::string& v, const std::string& s) {
                  try {
                      int val = std::stoi(v);
                      if (val < 1) {
                          throw std::runtime_error(s + " must be >= 1: " + v);
                      }
                      return val;
                  } catch (const std::invalid_argument&) {
                      throw std::runtime_error("Invalid " + s + ": " + v);
                  }
              });

    // RobotVision tracker parameter overrides
    auto parse_positive_double = [](const std::string& v, const std::string& s) {
        try {
            double val = std::stod(v);
            if (val < 0) {
                throw std::runtime_error(s + " must be >= 0: " + v);
            }
            return val;
        } catch (const std::invalid_argument&) {
            throw std::runtime_error("Invalid " + s + ": " + v);
        } catch (const std::out_of_range&) {
            throw std::runtime_error("Value out of range for " + s + ": " + v);
        }
    };
    apply_env(config.tracking.max_unreliable_time_s, tracker::env::MAX_UNRELIABLE_TIME_S,
              parse_positive_double);
    apply_env(config.tracking.non_measurement_time_dynamic_s,
              tracker::env::NON_MEASUREMENT_TIME_DYNAMIC_S, parse_positive_double);
    apply_env(config.tracking.non_measurement_time_static_s,
              tracker::env::NON_MEASUREMENT_TIME_STATIC_S, parse_positive_double);

    // Scenes overrides
    if (auto val = get_env(tracker::env::SCENES_SOURCE); val.has_value()) {
        if (val.value() == "file") {
            config.scenes.source = SceneSource::File;
        } else if (val.value() == "api") {
            config.scenes.source = SceneSource::Api;
        } else {
            throw std::runtime_error("Invalid " + std::string(tracker::env::SCENES_SOURCE) + ": " +
                                     val.value() + " (must be 'file' or 'api')");
        }
    }
    if (auto val = get_env(tracker::env::SCENES_FILE_PATH); val.has_value()) {
        config.scenes.file_path = val.value();
    }

    // Manager env var overrides
    auto env_mgr_url = get_env(tracker::env::MANAGER_URL);
    auto env_mgr_auth = get_env(tracker::env::MANAGER_AUTH_PATH);
    auto env_mgr_ca = get_env(tracker::env::MANAGER_CA_CERT_PATH);
    if (env_mgr_url.has_value() || env_mgr_auth.has_value() || env_mgr_ca.has_value()) {
        if (!config.infrastructure.manager.has_value()) {
            config.infrastructure.manager = ManagerConfig{};
        }
        auto& mgr = config.infrastructure.manager.value();
        if (env_mgr_url.has_value())
            mgr.url = env_mgr_url.value();
        if (env_mgr_auth.has_value())
            mgr.auth_path = env_mgr_auth.value();
        if (env_mgr_ca.has_value())
            mgr.ca_cert_path = env_mgr_ca.value();
    }

    // Re-validate after env overrides: API mode requires manager config
    if (config.scenes.source == SceneSource::Api) {
        if (!config.infrastructure.manager.has_value()) {
            throw std::runtime_error("Missing required config: infrastructure.manager (required "
                                     "when scenes.source='api')");
        }
        const auto& mgr = config.infrastructure.manager.value();
        if (mgr.url.empty() || mgr.auth_path.empty()) {
            throw std::runtime_error(
                "Invalid infrastructure.manager configuration: url and auth_path must be set "
                "and non-empty when scenes.source='api'");
        }
    }

    // OTLP env var overrides
    if (auto val = get_env(tracker::env::OTLP_ENDPOINT); val.has_value()) {
        if (!config.infrastructure.otlp.has_value()) {
            config.infrastructure.otlp = OtlpConfig{};
        }
        config.infrastructure.otlp->endpoint = val.value();
    }

    // Observability env var overrides
    apply_env(config.observability.metrics.enabled, tracker::env::METRICS_ENABLED, parse_bool);
    apply_env(config.observability.tracing.enabled, tracker::env::TRACING_ENABLED, parse_bool);
    auto parse_export_interval = [](const std::string& v, const std::string& s) {
        try {
            int val = std::stoi(v);
            if (val < 1) {
                throw std::runtime_error(s + " must be >= 1: " + v);
            }
            return val;
        } catch (const std::invalid_argument&) {
            throw std::runtime_error("Invalid " + s + ": " + v);
        } catch (const std::out_of_range&) {
            throw std::runtime_error("Value out of range for " + s + ": " + v);
        }
    };
    apply_env(config.observability.metrics.export_interval_s,
              tracker::env::METRICS_EXPORT_INTERVAL_S, parse_export_interval);
    apply_env(config.observability.tracing.export_interval_s,
              tracker::env::TRACING_EXPORT_INTERVAL_S, parse_export_interval);

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
