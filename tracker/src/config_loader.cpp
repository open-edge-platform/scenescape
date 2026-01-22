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
 */
std::optional<std::string> get_env(const char* name) {
    const char* value = std::getenv(name);
    if (value != nullptr) {
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
 * @brief Parse and validate port number from string.
 * @throws std::runtime_error if invalid or out of range
 */
int parse_port(const std::string& port_str, const std::string& source) {
    try {
        int port = std::stoi(port_str);
        if (port < 1024 || port > 65535) {
            throw std::runtime_error(source + " out of range: " + port_str +
                                     " (must be 1024-65535)");
        }
        return port;
    } catch (const std::invalid_argument&) {
        throw std::runtime_error("Invalid " + source + ": " + port_str);
    } catch (const std::out_of_range&) {
        throw std::runtime_error(source + " out of range: " + port_str);
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

    // Extract values from JSON with defaults
    ServiceConfig config;

    // Infrastructure - MQTT (required)
    const auto& infrastructure = config_doc["infrastructure"];
    const auto& mqtt = infrastructure["mqtt"];
    config.infrastructure.mqtt.host = mqtt["host"].GetString();
    config.infrastructure.mqtt.port = mqtt["port"].GetInt();
    if (mqtt.HasMember("insecure")) {
        config.infrastructure.mqtt.insecure = mqtt["insecure"].GetBool();
    }

    // Infrastructure - MQTT SSL (optional)
    if (mqtt.HasMember("ssl")) {
        const auto& ssl = mqtt["ssl"];
        SslConfig ssl_config;
        if (ssl.HasMember("ca_cert_path")) {
            ssl_config.ca_cert_path = ssl["ca_cert_path"].GetString();
        }
        if (ssl.HasMember("client_cert_path")) {
            ssl_config.client_cert_path = ssl["client_cert_path"].GetString();
        }
        if (ssl.HasMember("client_key_path")) {
            ssl_config.client_key_path = ssl["client_key_path"].GetString();
        }
        if (ssl.HasMember("verify_server")) {
            ssl_config.verify_server = ssl["verify_server"].GetBool();
        }
        config.infrastructure.mqtt.ssl = ssl_config;
    }

    // Infrastructure - Tracker Healthcheck (optional)
    if (infrastructure.HasMember("tracker")) {
        const auto& tracker = infrastructure["tracker"];
        if (tracker.HasMember("healthcheck")) {
            const auto& healthcheck = tracker["healthcheck"];
            if (healthcheck.HasMember("port")) {
                config.infrastructure.tracker.healthcheck.port = healthcheck["port"].GetInt();
            }
        }
    }

    // Observability - Logging (optional)
    if (config_doc.HasMember("observability")) {
        const auto& observability = config_doc["observability"];
        if (observability.HasMember("logging")) {
            const auto& logging = observability["logging"];
            if (logging.HasMember("level")) {
                config.observability.logging.level = logging["level"].GetString();
            }
        }
    }

    // Apply environment variable overrides
    if (auto env_log_level = get_env(tracker::env::LOG_LEVEL); env_log_level.has_value()) {
        config.observability.logging.level =
            parse_log_level(env_log_level.value(), tracker::env::LOG_LEVEL);
    }

    if (auto env_port = get_env(tracker::env::HEALTHCHECK_PORT); env_port.has_value()) {
        config.infrastructure.tracker.healthcheck.port =
            parse_port(env_port.value(), tracker::env::HEALTHCHECK_PORT);
    }

    return config;
}

} // namespace tracker
