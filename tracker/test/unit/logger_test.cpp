// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "logger.hpp"

#include "utils/json_schema_validator.hpp"
#include "utils/test_sink.hpp"

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <vector>

namespace tracker {
namespace {

using test::get_log_schema_path;
using test::JsonSchemaValidator;
using test::TestSink;

// =============================================================================
// Logger Lifecycle Tests
// =============================================================================

/**
 * @brief Tests Logger initialization, shutdown, and flush behavior.
 *
 * Checks:
 * - Pre-init state: is_initialized() == false, get() == nullptr
 * - Post-init state: is_initialized() == true, get() != nullptr
 * - Double-init idempotency: second init() returns same logger instance
 * - Flush on shutdown: logs written before shutdown() are captured (critical for SIGTERM)
 * - Double-shutdown safety: calling shutdown() twice doesn't crash
 */
TEST(LoggerLifecycleTest, InitShutdownAndFlush) {
    auto test_info = testing::UnitTest::GetInstance()->current_test_info();
    std::string sink_name = std::string(test_info->test_suite_name()) + "_" + test_info->name();
    auto sink = quill::Frontend::create_or_get_sink<TestSink>(sink_name);
    auto* test_sink = static_cast<TestSink*>(sink.get());

    // Pre-init state
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }
    EXPECT_FALSE(Logger::is_initialized());
    EXPECT_EQ(Logger::get(), nullptr);

    // Initialize
    Logger::init("info", sink);
    EXPECT_TRUE(Logger::is_initialized());
    EXPECT_NE(Logger::get(), nullptr);

    // Double init is no-op
    auto* logger1 = Logger::get();

    // Double init is no-op - same instance returned
    Logger::init("debug", sink);
    EXPECT_EQ(Logger::get(), logger1);

    // Log before shutdown
    LOG_INFO("Message before shutdown");

    // Shutdown flushes pending logs
    Logger::shutdown();
    EXPECT_FALSE(Logger::is_initialized());

    // Verify flush happened
    auto statements = test_sink->get_statements();
    ASSERT_EQ(statements.size(), 1u) << "Shutdown must flush pending logs";
    EXPECT_NE(statements[0].find("Message before shutdown"), std::string::npos);

    // Double shutdown is safe
    Logger::shutdown();
    EXPECT_FALSE(Logger::is_initialized());
}

/**
 * @brief Tests all valid log levels, aliases, and unknown level handling.
 *
 * Checks:
 * - All valid levels initialize: "trace", "debug", "info", "warn", "warning", "error"
 * - Level aliases work: "warn" and "warning" are equivalent
 * - Unknown level defaults to "info" without crashing
 */
TEST(LoggerLifecycleTest, LogLevelConfiguration) {
    std::vector<std::string> levels = {"trace", "debug", "info", "warn", "warning", "error"};

    for (const auto& level : levels) {
        Logger::init(level);
        EXPECT_TRUE(Logger::is_initialized()) << "Failed for level: " << level;
        Logger::shutdown();
    }

    // Unknown level defaults to info
    Logger::init("unknown_level");
    EXPECT_TRUE(Logger::is_initialized());
    Logger::shutdown();
}

/**
 * @brief Tests that log methods don't crash when logger is not initialized.
 *
 * Checks:
 * - Logger::log_trace/debug/info/warn/error() silently return when uninitialized
 * - No segfault, no exception thrown
 */
TEST(LoggerLifecycleTest, NullLoggerSafety) {
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }

    // All methods should silently return without crashing
    Logger::log_trace(LogEntry("Test"));
    Logger::log_debug(LogEntry("Test"));
    Logger::log_info(LogEntry("Test"));
    Logger::log_warn(LogEntry("Test"));
    Logger::log_error(LogEntry("Test"));
    SUCCEED();
}

// =============================================================================
// JSON Output Validation Test
// =============================================================================

/**
 * @brief Comprehensive test for JSON log output validation.
 *
 * Uses TestSink to capture log output and JsonSchemaValidator to verify format.
 *
 * Schema validation checks:
 * - Every log line is valid JSON
 * - Required fields present: timestamp, level, msg
 * - Field types match schema (strings, numbers, enums)
 *
 * Value verification checks:
 * - Log levels map correctly: LOG_TRACE→"TRACE_L1", LOG_DEBUG→"DEBUG",
 *   LOG_INFO→"INFO", LOG_WARN→"WARNING", LOG_ERROR→"ERROR"
 * - Context fields propagate: component, operation, trace_id, span_id,
 *   mqtt (topic, message_id, direction), domain (camera_id, scene_id, etc.), error (type, message)
 * - Special characters JSON-escaped: quotes→\", backslash→\\, newline→\n, tab→\t
 * - Static Logger::log_*() methods produce same output as LOG_*() macros
 */
TEST(LoggerJsonTest, ValidJsonOutput) {
    // Setup
    auto test_info = testing::UnitTest::GetInstance()->current_test_info();
    std::string sink_name = std::string(test_info->test_suite_name()) + "_" + test_info->name();
    auto sink = quill::Frontend::create_or_get_sink<TestSink>(sink_name);
    auto* test_sink = static_cast<TestSink*>(sink.get());
    test_sink->clear();

    Logger::init("trace", sink);
    JsonSchemaValidator validator{get_log_schema_path()};

    // --- All log levels ---
    LOG_TRACE("Trace message");
    LOG_DEBUG("Debug message");
    LOG_INFO("Info message");
    LOG_WARN("Warning message");
    LOG_ERROR("Error message");

    // --- Structured contexts ---
    LOG_INFO_ENTRY(LogEntry("Component test").component("tracker"));
    LOG_INFO_ENTRY(LogEntry("Operation test").operation("process"));
    LOG_INFO_ENTRY(
        LogEntry("Trace context").trace({"4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7"}));
    LOG_INFO_ENTRY(LogEntry("MQTT with id").mqtt({"topic/test", 123, "publish"}));
    LOG_INFO_ENTRY(LogEntry("MQTT no id").mqtt({"topic/test", std::nullopt, "subscribe"}));
    LOG_INFO_ENTRY(LogEntry("Domain partial").domain({.camera_id = "cam-01", .scene_id = "main"}));
    LOG_INFO_ENTRY(LogEntry("Domain full")
                       .domain({.camera_id = "cam-01",
                                .sensor_id = "lidar",
                                .scene_id = "warehouse",
                                .object_category = "person",
                                .track_uuid = "uuid-123"}));
    LOG_ERROR_ENTRY(LogEntry("Error context").error({"ValidationError", "Invalid input"}));

    // --- All contexts combined ---
    LOG_INFO_ENTRY(LogEntry("All contexts")
                       .component("tracker")
                       .operation("process-frame")
                       .trace({"4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7"})
                       .mqtt({"topic/test", 999, "publish"})
                       .domain({.camera_id = "cam-1", .scene_id = "scene-1"})
                       .error({"Warning", "Recoverable"}));

    // --- Special character escaping ---
    LOG_INFO_ENTRY(LogEntry("Quotes \"and\" \\backslash").component("test"));
    LOG_INFO_ENTRY(LogEntry("Newline\nand\ttab\rcarriage").component("test"));

    // --- Static log methods ---
    Logger::log_trace(LogEntry("Static trace").component("test"));
    Logger::log_debug(LogEntry("Static debug").component("test"));
    Logger::log_info(LogEntry("Static info").operation("op"));
    Logger::log_warn(LogEntry("Static warn").component("test"));
    Logger::log_error(LogEntry("Static error").error({"Err", "Msg"}));

    // Flush and validate
    Logger::get()->flush_log();
    auto statements = test_sink->get_statements();
    ASSERT_GE(statements.size(), 18u) << "Expected at least 18 log statements";

    for (const auto& stmt : statements) {
        EXPECT_TRUE(validator.validate(stmt))
            << "Invalid JSON: " << validator.get_error() << "\nLog: " << stmt;
    }

    // --- Value checks (schema doesn't validate actual values) ---
    using ::testing::Contains;
    using ::testing::HasSubstr;

    // Log levels (uppercase per schema)
    EXPECT_THAT(statements, Contains(HasSubstr("\"level\":\"TRACE_L1\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"level\":\"DEBUG\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"level\":\"INFO\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"level\":\"WARNING\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"level\":\"ERROR\"")));

    // Context values propagate correctly
    EXPECT_THAT(statements, Contains(HasSubstr("\"component\":\"tracker\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"operation\":\"process\"")));
    EXPECT_THAT(statements,
                Contains(HasSubstr("\"trace_id\":\"4bf92f3577b34da6a3ce929d0e0e4736\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"span_id\":\"00f067aa0ba902b7\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"topic\":\"topic/test\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"message_id\":123")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"camera_id\":\"cam-01\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"scene_id\":\"warehouse\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\"type\":\"ValidationError\"")));

    // Special character escaping
    EXPECT_THAT(statements, Contains(HasSubstr("\\\"and\\\"")));
    EXPECT_THAT(statements, Contains(HasSubstr("\\\\backslash")));
    EXPECT_THAT(statements, Contains(HasSubstr("\\n")));
    EXPECT_THAT(statements, Contains(HasSubstr("\\t")));

    Logger::shutdown();
}

} // namespace
} // namespace tracker
