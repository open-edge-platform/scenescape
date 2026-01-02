// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

// -----------------------------------------------------------------------------
// Structured JSON Logger for Tracker Service
//
// Design: Singleton pattern for state management, thin macros for compile-time
// format strings (required by Quill for zero-copy logging performance).
//
// Usage:
//   Logger::init("debug");  // or Logger::init_from_env();
//
//   // Simple logging (via macros - required by Quill for compile-time format)
//   LOG_INFO("Service started");
//   LOG_DEBUG("Processing {} items", count);
//
//   // Structured logging with context
//   LOG_INFO_ENTRY(LogEntry("MQTT connected").component("mqtt").mqtt({...}));
//
//   Logger::shutdown();
//
// Output (JSON lines to stdout):
//   {"timestamp":"2024-01-15T10:30:00.123Z","level":"INFO","msg":"Service started",
//    "service":"tracker","service_version":"0.1.0"}
// -----------------------------------------------------------------------------

#include <optional>
#include <string>
#include <string_view>

namespace tracker {

// Service metadata (compile-time constants)
// All values are injected by CMake via compile definitions
#ifndef TRACKER_SERVICE_NAME
    #define TRACKER_SERVICE_NAME "tracker"
#endif

#ifndef TRACKER_SERVICE_VERSION
    #define TRACKER_SERVICE_VERSION "dev"
#endif

#ifndef TRACKER_GIT_COMMIT
    #define TRACKER_GIT_COMMIT "unknown"
#endif

constexpr const char* SERVICE_NAME = TRACKER_SERVICE_NAME;
constexpr const char* SERVICE_VERSION = TRACKER_SERVICE_VERSION;
constexpr const char* GIT_COMMIT = TRACKER_GIT_COMMIT;

// -----------------------------------------------------------------------------
// Context structures for structured logging
// -----------------------------------------------------------------------------

struct MqttContext {
    std::string topic;
    std::optional<int> message_id;
    std::string direction; // "publish" | "subscribe" | "receive"
};

struct DomainContext {
    std::optional<std::string> camera_id;
    std::optional<std::string> sensor_id;
    std::optional<std::string> scene_id;
    std::optional<std::string> object_category;
    std::optional<std::string> track_uuid;
};

struct ErrorContext {
    std::string type;
    std::string message;
};

struct TraceContext {
    std::string trace_id;
    std::string span_id;
};

// -----------------------------------------------------------------------------
// LogEntry - Fluent builder for structured log messages
// -----------------------------------------------------------------------------

class LogEntry {
public:
    explicit LogEntry(std::string_view message) : msg_(message) {}

    LogEntry& component(std::string_view comp) {
        component_ = std::string(comp);
        return *this;
    }

    LogEntry& operation(std::string_view op) {
        operation_ = std::string(op);
        return *this;
    }

    LogEntry& trace(const TraceContext& ctx) {
        trace_ = ctx;
        return *this;
    }

    LogEntry& mqtt(const MqttContext& ctx) {
        mqtt_ = ctx;
        return *this;
    }

    LogEntry& domain(const DomainContext& ctx) {
        domain_ = ctx;
        return *this;
    }

    LogEntry& error(const ErrorContext& ctx) {
        error_ = ctx;
        return *this;
    }

    // Build the structured message payload
    [[nodiscard]] std::string build() const;

private:
    std::string msg_;
    std::optional<std::string> component_;
    std::optional<std::string> operation_;
    std::optional<TraceContext> trace_;
    std::optional<MqttContext> mqtt_;
    std::optional<DomainContext> domain_;
    std::optional<ErrorContext> error_;
};

} // namespace tracker

// Include Quill headers after our declarations
#include <quill/Backend.h>
#include <quill/Frontend.h>
#include <quill/Logger.h>
#include <quill/LogMacros.h>
#include <quill/sinks/ConsoleSink.h>

namespace tracker {

// -----------------------------------------------------------------------------
// Logger - Singleton manager for Quill logger
// -----------------------------------------------------------------------------

class Logger {
public:
    // Non-copyable, non-movable
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;
    Logger(Logger&&) = delete;
    Logger& operator=(Logger&&) = delete;

    // Initialize logger with specified level
    static void init(std::string_view level = "info");

    // Shutdown logger and flush all pending messages
    static void shutdown();

    // Check if logger is initialized
    [[nodiscard]] static bool is_initialized();

    // Get underlying Quill logger (for macros)
    [[nodiscard]] static quill::Logger* get();

    // Structured logging methods (for LogEntry)
    static void log_trace(const LogEntry& entry);
    static void log_debug(const LogEntry& entry);
    static void log_info(const LogEntry& entry);
    static void log_warn(const LogEntry& entry);
    static void log_error(const LogEntry& entry);

private:
    Logger() = default;
    ~Logger() = default;

    static Logger& instance();

    quill::Logger* logger_ = nullptr;
    bool initialized_ = false;
};

} // namespace tracker

// -----------------------------------------------------------------------------
// Logging macros - thin wrappers for compile-time format strings
//
// Note: Quill requires compile-time format strings for its zero-copy design.
// These macros provide the cleanest API while meeting Quill's requirements.
// -----------------------------------------------------------------------------

// Undefine Quill's shorthand macros to avoid conflicts
#ifdef LOG_TRACE
    #undef LOG_TRACE
#endif
#ifdef LOG_DEBUG
    #undef LOG_DEBUG
#endif
#ifdef LOG_INFO
    #undef LOG_INFO
#endif
#ifdef LOG_WARN
    #undef LOG_WARN
#endif
#ifdef LOG_WARNING
    #undef LOG_WARNING
#endif
#ifdef LOG_ERROR
    #undef LOG_ERROR
#endif

// Simple logging macros (use global singleton logger)
#define LOG_TRACE(fmt, ...) QUILL_LOG_TRACE_L1(tracker::Logger::get(), fmt, ##__VA_ARGS__)

#define LOG_DEBUG(fmt, ...) QUILL_LOG_DEBUG(tracker::Logger::get(), fmt, ##__VA_ARGS__)

#define LOG_INFO(fmt, ...) QUILL_LOG_INFO(tracker::Logger::get(), fmt, ##__VA_ARGS__)

#define LOG_WARN(fmt, ...) QUILL_LOG_WARNING(tracker::Logger::get(), fmt, ##__VA_ARGS__)

#define LOG_ERROR(fmt, ...) QUILL_LOG_ERROR(tracker::Logger::get(), fmt, ##__VA_ARGS__)

// Structured logging macros (for LogEntry)
#define LOG_TRACE_ENTRY(entry) tracker::Logger::log_trace(entry)
#define LOG_DEBUG_ENTRY(entry) tracker::Logger::log_debug(entry)
#define LOG_INFO_ENTRY(entry) tracker::Logger::log_info(entry)
#define LOG_WARN_ENTRY(entry) tracker::Logger::log_warn(entry)
#define LOG_ERROR_ENTRY(entry) tracker::Logger::log_error(entry)
