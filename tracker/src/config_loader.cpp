// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"

#include "env_vars.hpp"
#include "json_utils.hpp"

#include <cmath>
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

/// @throws std::runtime_error if not an integer in [1, kMaxObservationProcessorTimeoutMs]
int parse_timeout_ms(const std::string& value, const std::string& source) {
    try {
        int timeout = std::stoi(value);
        if (timeout < 1 || timeout > kMaxObservationProcessorTimeoutMs) {
            throw std::runtime_error(source + " must be in [1, " +
                                     std::to_string(kMaxObservationProcessorTimeoutMs) +
                                     "]: " + value);
        }
        return timeout;
    } catch (const std::invalid_argument&) {
        throw std::runtime_error("Invalid " + source + ": " + value);
    } catch (const std::out_of_range&) {
        throw std::runtime_error("Value out of range for " + source + ": " + value);
    }
}

void load_observation_processor(rapidjson::Document& config_doc, ServiceConfig& config) {
    using rapidjson::GetValueByPointer;
    using rapidjson::GetValueByPointerWithDefault;

    config.tracking.experimental_observation_processor =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_EXPERIMENTAL_OBSERVATION_PROCESSOR,
                                     false)
            .GetBool();
    if (auto* mode = GetValueByPointer(config_doc, json::TRACKING_OBSERVATION_PROCESSOR_MODE)) {
        config.tracking.observation_processor_mode = parseConditioningMode(mode->GetString());
    }

    if (!GetValueByPointer(config_doc, json::INFRASTRUCTURE_OBSERVATION_PROCESSOR)) {
        return;
    }
    // host and port are required by the schema
    RemoteObservationProcessorConfig remote;
    remote.host =
        GetValueByPointer(config_doc, json::INFRASTRUCTURE_OBSERVATION_PROCESSOR_HOST)->GetString();
    remote.port =
        GetValueByPointer(config_doc, json::INFRASTRUCTURE_OBSERVATION_PROCESSOR_PORT)->GetInt();
    remote.insecure = GetValueByPointerWithDefault(
                          config_doc, json::INFRASTRUCTURE_OBSERVATION_PROCESSOR_INSECURE, false)
                          .GetBool();
    if (auto* ca = GetValueByPointer(config_doc,
                                     json::INFRASTRUCTURE_OBSERVATION_PROCESSOR_CA_CERT_PATH)) {
        remote.ca_cert_path = ca->GetString();
    }
    remote.timeout_ms = GetValueByPointerWithDefault(
                            config_doc, json::INFRASTRUCTURE_OBSERVATION_PROCESSOR_TIMEOUT_MS,
                            kDefaultObservationProcessorTimeoutMs)
                            .GetInt();
    config.infrastructure.observation_processor = remote;
}

void apply_observation_processor_env(ServiceConfig& config) {
    apply_env(config.tracking.experimental_observation_processor,
              tracker::env::EXPERIMENTAL_OBSERVATION_PROCESSOR, parse_bool);
    if (auto val = get_env(tracker::env::OBSERVATION_PROCESSOR_MODE); val.has_value()) {
        config.tracking.observation_processor_mode = parseConditioningMode(val.value());
    }

    auto host = get_env(tracker::env::OBSERVATION_PROCESSOR_HOST);
    auto port = get_env(tracker::env::OBSERVATION_PROCESSOR_PORT);
    auto insecure = get_env(tracker::env::OBSERVATION_PROCESSOR_INSECURE);
    auto ca_cert = get_env(tracker::env::OBSERVATION_PROCESSOR_CA_CERT);
    auto timeout = get_env(tracker::env::OBSERVATION_PROCESSOR_TIMEOUT_MS);
    if (!host && !port && !insecure && !ca_cert && !timeout) {
        return;
    }
    if (!config.infrastructure.observation_processor.has_value()) {
        config.infrastructure.observation_processor = RemoteObservationProcessorConfig{};
    }
    auto& remote = config.infrastructure.observation_processor.value();
    if (host) {
        remote.host = *host;
    }
    if (port) {
        remote.port = parse_port(*port, tracker::env::OBSERVATION_PROCESSOR_PORT);
    }
    if (insecure) {
        remote.insecure = parse_bool(*insecure, tracker::env::OBSERVATION_PROCESSOR_INSECURE);
    }
    if (ca_cert) {
        remote.ca_cert_path = *ca_cert;
    }
    if (timeout) {
        remote.timeout_ms =
            parse_timeout_ms(*timeout, tracker::env::OBSERVATION_PROCESSOR_TIMEOUT_MS);
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

    if (auto* method = GetValueByPointer(config_doc, json::TRACKING_ASSOCIATION_METHOD)) {
        if (!method->IsString()) {
            throw std::runtime_error("Invalid association method: expected string");
        }
        config.tracking.association.method = parseAssociationMethod(method->GetString());
    }
    config.tracking.association.gate_probability =
        GetValueByPointerWithDefault(config_doc, json::TRACKING_ASSOCIATION_GATE_PROBABILITY,
                                     kDefaultAssociationGateProbability)
            .GetDouble();
    // RapidJSON validates draft-04, which ignores the schema's numeric exclusiveMinimum.
    if (!(config.tracking.association.gate_probability > 0.0 &&
          config.tracking.association.gate_probability <= 1.0)) {
        throw std::runtime_error("tracking.association.gate_probability must be in (0, 1]: " +
                                 std::to_string(config.tracking.association.gate_probability));
    }
    // Without max_radius_m the default depends on the method, so it is resolved after the env
    // overrides below. Validate here too: schema minimum:0 is not enough if validation is skipped
    // or a non-finite value slips through.
    std::optional<double> association_max_radius_m;
    if (auto* max_radius_m =
            GetValueByPointer(config_doc, json::TRACKING_ASSOCIATION_MAX_RADIUS_M)) {
        if (!max_radius_m->IsNumber()) {
            throw std::runtime_error("tracking.association.max_radius_m must be a number");
        }
        const double radius = max_radius_m->GetDouble();
        if (!std::isfinite(radius) || radius < 0.0) {
            throw std::runtime_error(
                "tracking.association.max_radius_m must be a finite number >= 0: " +
                std::to_string(radius));
        }
        association_max_radius_m = radius;
    }
    load_observation_processor(config_doc, config);

    // NTP configuration (optional; server empty/missing = use OS clock)
    if (GetValueByPointer(config_doc, json::INFRASTRUCTURE_NTP)) {
        NtpConfig ntp_config;
        if (auto* val = GetValueByPointer(config_doc, json::INFRASTRUCTURE_NTP_SERVER)) {
            if (val->IsString() && val->GetStringLength() > 0) {
                ntp_config.server = val->GetString();
            }
        }
        ntp_config.sync_interval_s =
            GetValueByPointerWithDefault(config_doc, json::INFRASTRUCTURE_NTP_SYNC_INTERVAL_S,
                                         kDefaultNtpSyncIntervalS)
                .GetInt();
        if (!ntp_config.server.empty()) {
            config.infrastructure.ntp = ntp_config;
        }
    }

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

    if (auto val = get_env(tracker::env::ASSOCIATION_METHOD); val.has_value()) {
        config.tracking.association.method = parseAssociationMethod(val.value());
    }
    apply_env(config.tracking.association.gate_probability,
              tracker::env::ASSOCIATION_GATE_PROBABILITY,
              [](const std::string& v, const std::string& s) {
                  try {
                      std::size_t parsed = 0;
                      double probability = std::stod(v, &parsed);
                      if (parsed != v.size()) {
                          throw std::runtime_error("Invalid " + s + ": " + v);
                      }
                      if (!std::isfinite(probability) || probability <= 0.0 || probability > 1.0) {
                          throw std::runtime_error(s + " must be in (0, 1]: " + v);
                      }
                      return probability;
                  } catch (const std::invalid_argument&) {
                      throw std::runtime_error("Invalid " + s + ": " + v);
                  } catch (const std::out_of_range&) {
                      throw std::runtime_error("Value out of range for " + s + ": " + v);
                  }
              });
    apply_env(association_max_radius_m, tracker::env::ASSOCIATION_MAX_RADIUS_M,
              [](const std::string& v, const std::string& s) {
                  try {
                      std::size_t parsed = 0;
                      double radius = std::stod(v, &parsed);
                      if (parsed != v.size() || !std::isfinite(radius) || radius < 0.0) {
                          throw std::runtime_error(s + " must be a finite number >= 0: " + v);
                      }
                      return radius;
                  } catch (const std::invalid_argument&) {
                      throw std::runtime_error("Invalid " + s + ": " + v);
                  } catch (const std::out_of_range&) {
                      throw std::runtime_error("Value out of range for " + s + ": " + v);
                  }
              });
    config.tracking.association.max_radius_m =
        association_max_radius_m.value_or(defaultMaxRadiusM(config.tracking.association.method));
    apply_observation_processor_env(config);

    // NTP overrides: env vars take precedence;
    if (auto val = get_env(tracker::env::NTP_SERVER); val.has_value()) {
        if (!config.infrastructure.ntp.has_value()) {
            config.infrastructure.ntp = NtpConfig{};
        }
        config.infrastructure.ntp->server = val.value();
    }
    if (auto val = get_env(tracker::env::NTP_SYNC_INTERVAL_S); val.has_value()) {
        try {
            int interval = std::stoi(*val);
            if (interval < 60) {
                throw std::runtime_error(std::string(tracker::env::NTP_SYNC_INTERVAL_S) +
                                         " must be >= 60: " + *val);
            }
            if (!config.infrastructure.ntp.has_value()) {
                config.infrastructure.ntp = NtpConfig{};
            }
            config.infrastructure.ntp->sync_interval_s = interval;
        } catch (const std::invalid_argument&) {
            throw std::runtime_error("Invalid " + std::string(tracker::env::NTP_SYNC_INTERVAL_S) +
                                     ": " + *val);
        } catch (const std::out_of_range&) {
            throw std::runtime_error("Value out of range for " +
                                     std::string(tracker::env::NTP_SYNC_INTERVAL_S) + ": " + *val);
        }
    }
    // Discard an ntp config that has no server (can happen when only the interval env var is set).
    if (config.infrastructure.ntp.has_value() && config.infrastructure.ntp->server.empty()) {
        config.infrastructure.ntp = std::nullopt;
    }

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
