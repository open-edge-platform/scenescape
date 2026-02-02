// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "logger.hpp"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <sstream>

namespace tracker {

namespace {

quill::LogLevel to_quill_level(std::string_view level_str) {
    std::string lower(level_str);
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return std::tolower(c); });

    if (lower == "trace")
        return quill::LogLevel::TraceL1;
    if (lower == "debug")
        return quill::LogLevel::Debug;
    if (lower == "info")
        return quill::LogLevel::Info;
    if (lower == "warn" || lower == "warning")
        return quill::LogLevel::Warning;
    if (lower == "error")
        return quill::LogLevel::Error;

    return quill::LogLevel::Info; // Default
}

// Escape string for JSON
std::string json_escape(std::string_view str) {
    std::string result;
    result.reserve(str.size());
    for (char c : str) {
        switch (c) {
            case '"':
                result += "\\\"";
                break;
            case '\\':
                result += "\\\\";
                break;
            case '\n':
                result += "\\n";
                break;
            case '\r':
                result += "\\r";
                break;
            case '\t':
                result += "\\t";
                break;
            default:
                result += c;
        }
    }
    return result;
}

} // namespace

// --------------------------------------------------------------------------
// BackendHandle static members
// --------------------------------------------------------------------------

std::mutex BackendHandle::mutex_;
std::weak_ptr<BackendHandle> BackendHandle::weak_instance_;

// --------------------------------------------------------------------------
// Logger singleton implementation
// --------------------------------------------------------------------------

Logger& Logger::instance() {
    static Logger inst;
    return inst;
}

void Logger::init(std::string_view level, std::shared_ptr<quill::Sink> sink) {
    auto& inst = instance();
    if (inst.initialized_) {
        return; // Already initialized
    }

    // Acquire backend handle (starts backend if first user)
    inst.backend_ = BackendHandle::acquire();

    // JSON format pattern for structured logging (compile-time string literal concatenation)
    // Note: {{ and }} escape braces in Quill's pattern formatter
    static constexpr const char* json_pattern =
        "{{\"timestamp\":\"%(time)\",\"level\":\"%(log_level)\",\"msg\":\"%(message)\""
        ",\"service\":\"" TRACKER_SERVICE_NAME "\",\"version\":\"" TRACKER_SERVICE_VERSION
        "\",\"commit\":\"" TRACKER_GIT_COMMIT "\"}}";

    quill::PatternFormatterOptions formatter_options{
        json_pattern,
        "%Y-%m-%dT%H:%M:%S.%QmsZ", // RFC3339/ISO8601 UTC timestamp
        quill::Timezone::GmtTime};

    inst.logger_ =
        quill::Frontend::create_or_get_logger(SERVICE_NAME, std::move(sink), formatter_options);
    inst.logger_->set_log_level(to_quill_level(level));
    inst.initialized_ = true;
}

void Logger::shutdown() {
    auto& inst = instance();
    if (inst.logger_) {
        inst.logger_->flush_log();
        quill::Frontend::remove_logger(inst.logger_);
        inst.logger_ = nullptr;
    }
    // Release backend handle (stops backend if last user)
    inst.backend_.reset();
    inst.initialized_ = false;
}

bool Logger::is_initialized() {
    return instance().initialized_;
}

quill::Logger* Logger::get() {
    return instance().logger_;
}

// Structured logging methods
void Logger::log_trace(const LogEntry& entry) {
    if (auto* l = instance().logger_) {
        LOG_TRACE_L1(l, "{}", entry.build());
    }
}

void Logger::log_debug(const LogEntry& entry) {
    if (auto* l = instance().logger_) {
        QUILL_LOG_DEBUG(l, "{}", entry.build());
    }
}

void Logger::log_info(const LogEntry& entry) {
    if (auto* l = instance().logger_) {
        QUILL_LOG_INFO(l, "{}", entry.build());
    }
}

void Logger::log_warn(const LogEntry& entry) {
    if (auto* l = instance().logger_) {
        QUILL_LOG_WARNING(l, "{}", entry.build());
    }
}

void Logger::log_error(const LogEntry& entry) {
    if (auto* l = instance().logger_) {
        QUILL_LOG_ERROR(l, "{}", entry.build());
    }
}

// --------------------------------------------------------------------------
// LogEntry implementation
// --------------------------------------------------------------------------

std::string LogEntry::build() const {
    std::ostringstream extra;

    // Add optional fields as JSON fragments
    if (component_) {
        extra << ",\"component\":\"" << json_escape(*component_) << "\"";
    }
    if (operation_) {
        extra << ",\"operation\":\"" << json_escape(*operation_) << "\"";
    }
    if (trace_) {
        extra << ",\"trace_id\":\"" << json_escape(trace_->trace_id) << "\"";
        extra << ",\"span_id\":\"" << json_escape(trace_->span_id) << "\"";
    }
    if (mqtt_) {
        extra << ",\"mqtt\":{\"topic\":\"" << json_escape(mqtt_->topic) << "\"";
        if (mqtt_->message_id) {
            extra << ",\"message_id\":" << *mqtt_->message_id;
        }
        extra << ",\"direction\":\"" << json_escape(mqtt_->direction) << "\"}";
    }
    if (domain_) {
        extra << ",\"domain\":{";
        bool first = true;
        if (domain_->camera_id) {
            extra << "\"camera_id\":\"" << json_escape(*domain_->camera_id) << "\"";
            first = false;
        }
        if (domain_->sensor_id) {
            if (!first)
                extra << ",";
            extra << "\"sensor_id\":\"" << json_escape(*domain_->sensor_id) << "\"";
            first = false;
        }
        if (domain_->scene_id) {
            if (!first)
                extra << ",";
            extra << "\"scene_id\":\"" << json_escape(*domain_->scene_id) << "\"";
            first = false;
        }
        if (domain_->object_category) {
            if (!first)
                extra << ",";
            extra << "\"object_category\":\"" << json_escape(*domain_->object_category) << "\"";
            first = false;
        }
        if (domain_->track_uuid) {
            if (!first)
                extra << ",";
            extra << "\"track_uuid\":\"" << json_escape(*domain_->track_uuid) << "\"";
        }
        extra << "}";
    }
    if (error_) {
        extra << ",\"error\":{\"type\":\"" << json_escape(error_->type) << "\",\"message\":\""
              << json_escape(error_->message) << "\"}";
    }

    // Return message + extra JSON fields
    std::string extra_str = extra.str();
    if (extra_str.empty()) {
        return json_escape(msg_); // Pattern closes the quote
    }
    // Structured: add dummy field to absorb pattern's closing quote
    return json_escape(msg_) + "\"" + extra_str + ",\"_\":\"";
}

} // namespace tracker
