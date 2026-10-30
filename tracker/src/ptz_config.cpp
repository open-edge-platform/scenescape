// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_config.hpp"

#include "config_loader.hpp"
#include "env_vars.hpp"

#include <cmath>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>

#include <rapidjson/document.h>
#include <rapidjson/pointer.h>

namespace tracker {

namespace {

constexpr size_t kMaxTopicSegmentLength = 256;
constexpr size_t kMaxRunIdLength = 128;

std::optional<std::string> envValue(const char* name) {
    const char* value = std::getenv(name);
    if (value != nullptr && value[0] != '\0') {
        return std::string(value);
    }
    return std::nullopt;
}

bool parseEnvBool(const std::string& value, const char* name) {
    if (value == "true" || value == "1" || value == "yes") {
        return true;
    }
    if (value == "false" || value == "0" || value == "no") {
        return false;
    }
    throw std::runtime_error(std::string("Invalid ") + name + ": " + value +
                             " (must be true/false, 1/0, or yes/no)");
}

double parseEnvDouble(const std::string& value, const char* name) {
    size_t consumed = 0;
    double parsed = 0.0;
    try {
        parsed = std::stod(value, &consumed);
    } catch (const std::exception&) {
        throw std::runtime_error(std::string("Invalid ") + name + ": " + value);
    }
    if (consumed != value.size() || !std::isfinite(parsed)) {
        throw std::runtime_error(std::string("Invalid ") + name + ": " + value);
    }
    return parsed;
}

int parseEnvInt(const std::string& value, const char* name) {
    size_t consumed = 0;
    int parsed = 0;
    try {
        parsed = std::stoi(value, &consumed);
    } catch (const std::exception&) {
        throw std::runtime_error(std::string("Invalid ") + name + ": " + value);
    }
    if (consumed != value.size()) {
        throw std::runtime_error(std::string("Invalid ") + name + ": " + value);
    }
    return parsed;
}

bool isRunId(const std::string& run_id) {
    if (run_id.empty() || run_id.size() > kMaxRunIdLength) {
        return false;
    }
    for (char c : run_id) {
        const bool allowed = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                             (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
        if (!allowed) {
            return false;
        }
    }
    return true;
}

bool isTopicSegment(std::string_view value) {
    return !value.empty() && value.size() <= kMaxTopicSegmentLength &&
           value.find_first_of(std::string_view("/+#\0", 4)) == std::string_view::npos;
}

void requireBound(const std::optional<double>& value, const char* key, bool allow_zero) {
    if (!value.has_value()) {
        throw std::runtime_error(std::string("Missing required PTZ configuration: ptz.") + key);
    }
    if (!std::isfinite(*value) || (allow_zero ? *value < 0.0 : *value <= 0.0)) {
        throw std::runtime_error(std::string("ptz.") + key + " must be a finite number " +
                                 (allow_zero ? ">= 0" : "> 0"));
    }
}

void applyOptionalDouble(std::optional<double>& field, const char* env_name) {
    if (auto value = envValue(env_name)) {
        field = parseEnvDouble(*value, env_name);
    }
}

} // namespace

namespace detail {

void load_ptz_section(const rapidjson::Document& config_doc, PtzConfig& ptz) {
    auto at = [&config_doc](const char* pointer) {
        return rapidjson::Pointer(pointer).Get(config_doc);
    };
    auto boolean = [&](const char* pointer, bool& field) {
        if (const auto* value = at(pointer); value && value->IsBool()) {
            field = value->GetBool();
        }
    };
    auto number = [&](const char* pointer, std::optional<double>& field) {
        if (const auto* value = at(pointer); value && value->IsNumber()) {
            field = value->GetDouble();
        }
    };
    boolean(json::PTZ_ENABLED, ptz.enabled);
    boolean(json::PTZ_SHADOW_MODE, ptz.shadow_mode);
    number(json::PTZ_MAX_POSE_AGE_S, ptz.max_pose_age_s);
    number(json::PTZ_MAX_CLOCK_OFFSET_S, ptz.max_clock_offset_s);
    number(json::PTZ_MAX_DETECTION_PIPELINE_LATENCY_S, ptz.max_detection_pipeline_latency_s);
    number(json::PTZ_MAX_DETECTION_TIMESTAMP_UNCERTAINTY_S,
           ptz.max_detection_timestamp_uncertainty_s);
    if (const auto* value = at(json::PTZ_ASSIGNMENTS_PATH); value && value->IsString()) {
        ptz.assignments_path = value->GetString();
    }
    if (const auto* value = at(json::PTZ_SHADOW_RUN_ID); value && value->IsString()) {
        ptz.shadow.run_id = value->GetString();
    }
    if (const auto* value = at(json::PTZ_SHADOW_SAMPLE_EVERY_N); value && value->IsInt()) {
        ptz.shadow.sample_every_n = value->GetInt();
    }
    boolean(json::PTZ_SHADOW_PER_DECISION, ptz.shadow.per_decision);
}

void apply_ptz_env_overrides(PtzConfig& ptz) {
    if (auto value = envValue(env::PTZ_ENABLED)) {
        ptz.enabled = parseEnvBool(*value, env::PTZ_ENABLED);
    }
    if (auto value = envValue(env::PTZ_SHADOW_MODE)) {
        ptz.shadow_mode = parseEnvBool(*value, env::PTZ_SHADOW_MODE);
    }
    applyOptionalDouble(ptz.max_pose_age_s, env::PTZ_MAX_POSE_AGE_S);
    applyOptionalDouble(ptz.max_clock_offset_s, env::PTZ_MAX_CLOCK_OFFSET_S);
    applyOptionalDouble(ptz.max_detection_pipeline_latency_s,
                        env::PTZ_MAX_DETECTION_PIPELINE_LATENCY_S);
    applyOptionalDouble(ptz.max_detection_timestamp_uncertainty_s,
                        env::PTZ_MAX_DETECTION_TIMESTAMP_UNCERTAINTY_S);
    if (auto value = envValue(env::PTZ_ASSIGNMENTS_PATH)) {
        ptz.assignments_path = *value;
    }
    if (auto value = envValue(env::PTZ_SHADOW_RUN_ID)) {
        ptz.shadow.run_id = *value;
    }
    if (auto value = envValue(env::PTZ_SHADOW_SAMPLE_EVERY_N)) {
        ptz.shadow.sample_every_n = parseEnvInt(*value, env::PTZ_SHADOW_SAMPLE_EVERY_N);
    }
    if (auto value = envValue(env::PTZ_SHADOW_PER_DECISION)) {
        ptz.shadow.per_decision = parseEnvBool(*value, env::PTZ_SHADOW_PER_DECISION);
    }
}

void validate_ptz_config(const ServiceConfig& config) {
    const auto& ptz = config.ptz;
    if (ptz.enabled && ptz.shadow_mode) {
        throw std::runtime_error(std::string(env::PTZ_ENABLED) + " and " + env::PTZ_SHADOW_MODE +
                                 " (ptz.enabled, ptz.shadow_mode) are mutually exclusive");
    }
    if (ptz.mode() == PtzMode::Off) {
        return;
    }
    requireBound(ptz.max_pose_age_s, "max_pose_age_s", false);
    requireBound(ptz.max_clock_offset_s, "max_clock_offset_s", false);
    requireBound(ptz.max_detection_pipeline_latency_s, "max_detection_pipeline_latency_s", false);
    requireBound(ptz.max_detection_timestamp_uncertainty_s, "max_detection_timestamp_uncertainty_s",
                 true);
    if (!config.infrastructure.ntp.has_value()) {
        throw std::runtime_error(
            "PTZ pose consumption requires NTP clock synchronisation (infrastructure.ntp or " +
            std::string(env::NTP_SERVER) + ")");
    }
    if (ptz.assignments_path.empty()) {
        throw std::runtime_error("PTZ pose consumption requires ptz.assignments_path");
    }
    if (!isRunId(ptz.shadow.run_id)) {
        throw std::runtime_error("ptz.shadow.run_id must be 1-128 characters of [A-Za-z0-9._-]");
    }
    if (ptz.shadow.sample_every_n < 1) {
        throw std::runtime_error("ptz.shadow.sample_every_n must be an integer >= 1");
    }
}

} // namespace detail

namespace ptz {

Assignments parseAssignments(std::string_view json_text) {
    rapidjson::Document doc;
    if (doc.Parse(json_text.data(), json_text.size()).HasParseError() || !doc.IsObject()) {
        throw std::runtime_error("Positioning assignment manifest must be a JSON object");
    }
    Assignments assignments;
    for (auto it = doc.MemberBegin(); it != doc.MemberEnd(); ++it) {
        std::string_view source_id(it->name.GetString(), it->name.GetStringLength());
        if (source_id.starts_with('$')) {
            continue;
        }
        if (!isTopicSegment(source_id) || !it->value.IsString() ||
            !isTopicSegment({it->value.GetString(), it->value.GetStringLength()})) {
            throw std::runtime_error("Assignment '" + std::string(source_id) +
                                     "' must map a source_id to a resolver_id topic segment");
        }
        assignments.emplace(std::string(source_id),
                            std::string(it->value.GetString(), it->value.GetStringLength()));
    }
    return assignments;
}

Assignments loadAssignments(const std::filesystem::path& path) {
    std::ifstream ifs(path);
    if (!ifs.is_open()) {
        throw std::runtime_error("Cannot read positioning assignment manifest " + path.string());
    }
    std::ostringstream content;
    content << ifs.rdbuf();
    try {
        return parseAssignments(content.str());
    } catch (const std::runtime_error& error) {
        throw std::runtime_error("Positioning assignment manifest " + path.string() + ": " +
                                 error.what());
    }
}

} // namespace ptz

} // namespace tracker
