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

// Service metadata (compile-time constants)
// All values come from version.hpp (injected by CMake via compile definitions)
#include "version.hpp"

namespace tracker {

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
#include <quill/sinks/Sink.h>

#include <mutex>

namespace tracker {

// -----------------------------------------------------------------------------
// BackendHandle - RAII handle for Quill backend lifecycle
//
// Uses weak_ptr/shared_ptr pattern for reference counting.
// First handle starts the backend, last handle stops it.
// Thread-safe via mutex protection of the weak_ptr.
// -----------------------------------------------------------------------------

class BackendHandle {
public:
    ~BackendHandle() { quill::Backend::stop(); }

    // Non-copyable (use shared_ptr)
    BackendHandle(const BackendHandle&) = delete;
    BackendHandle& operator=(const BackendHandle&) = delete;

    /**
     * @brief Acquire a shared handle to the Quill backend.
     *
     * Starts the backend if this is the first handle.
     * Thread-safe via internal mutex.
     *
     * @return Shared pointer to backend handle
     */
    [[nodiscard]] static std::shared_ptr<BackendHandle> acquire() {
        std::lock_guard<std::mutex> lock(mutex_);
        auto handle = weak_instance_.lock();
        if (!handle) {
            handle = std::shared_ptr<BackendHandle>(new BackendHandle());
            weak_instance_ = handle;
        }
        return handle;
    }

private:
    BackendHandle() {
        quill::BackendOptions options;
        quill::Backend::start(options);
    }

    static std::mutex mutex_;
    static std::weak_ptr<BackendHandle> weak_instance_;
};

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

    // Initialize logger with specified level and optional custom sink (for testing)
    static void init(std::string_view level = "info",
                     std::shared_ptr<quill::Sink> sink =
                         quill::Frontend::create_or_get_sink<quill::ConsoleSink>("console"));

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

    // Check if debug logging is enabled (for conditional expensive computations)
    [[nodiscard]] static bool should_log_debug();

private:
    Logger() = default;
    ~Logger() = default;

    static Logger& instance();

    std::shared_ptr<BackendHandle> backend_;
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
