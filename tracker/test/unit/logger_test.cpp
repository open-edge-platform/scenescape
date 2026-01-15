// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "logger.hpp"

#include <gtest/gtest.h>

namespace tracker {
namespace {

class LoggerTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("debug"); }

    void TearDown() override { Logger::shutdown(); }
};

TEST_F(LoggerTest, Initialization) {
    EXPECT_TRUE(Logger::is_initialized());
    EXPECT_NE(Logger::get(), nullptr);
}

TEST_F(LoggerTest, SimpleLogging) {
    // These should not throw - using macros for compile-time format
    LOG_TRACE("Trace message");
    LOG_DEBUG("Debug message");
    LOG_INFO("Info message");
    LOG_WARN("Warning message");
    LOG_ERROR("Error message");
}

TEST_F(LoggerTest, FormattedLogging) {
    // These should not throw
    LOG_INFO("Value: {}", 42);
    LOG_DEBUG("String: {}, Int: {}", "test", 123);
}

TEST_F(LoggerTest, LogEntryBuilder) {
    LogEntry entry("Test message");

    std::string result = entry.component("test-component").operation("test-op").build();

    EXPECT_FALSE(result.empty());
    EXPECT_NE(result.find("component"), std::string::npos);
    EXPECT_NE(result.find("test-component"), std::string::npos);
    EXPECT_NE(result.find("operation"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryWithMqttContext) {
    MqttContext mqtt{"test/topic", 123, "publish"};
    LogEntry entry("MQTT message");

    std::string result = entry.mqtt(mqtt).build();

    EXPECT_NE(result.find("mqtt"), std::string::npos);
    EXPECT_NE(result.find("test/topic"), std::string::npos);
    EXPECT_NE(result.find("123"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryWithDomainContext) {
    DomainContext domain{.camera_id = "cam-01", .scene_id = "scene-main"};
    LogEntry entry("Domain message");

    std::string result = entry.domain(domain).build();

    EXPECT_NE(result.find("domain"), std::string::npos);
    EXPECT_NE(result.find("cam-01"), std::string::npos);
    EXPECT_NE(result.find("scene-main"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryWithErrorContext) {
    ErrorContext err{"TestError", "Something went wrong"};
    LogEntry entry("Error occurred");

    std::string result = entry.error(err).build();

    EXPECT_NE(result.find("error"), std::string::npos);
    EXPECT_NE(result.find("TestError"), std::string::npos);
    EXPECT_NE(result.find("Something went wrong"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryWithTraceContext) {
    TraceContext trace{"trace-123", "span-456"};
    LogEntry entry("Traced message");

    std::string result = entry.trace(trace).build();

    EXPECT_NE(result.find("trace_id"), std::string::npos);
    EXPECT_NE(result.find("trace-123"), std::string::npos);
    EXPECT_NE(result.find("span_id"), std::string::npos);
    EXPECT_NE(result.find("span-456"), std::string::npos);
}

TEST_F(LoggerTest, StructuredLogging) {
    // These should not throw
    LOG_INFO_ENTRY(LogEntry("Structured info").component("test"));
    LOG_DEBUG_ENTRY(LogEntry("Structured debug").operation("test-op"));
    LOG_ERROR_ENTRY(LogEntry("Structured error").error({"Type", "Message"}));
}

TEST_F(LoggerTest, JsonEscaping) {
    LogEntry entry("Message with \"quotes\" and \\backslash");
    std::string result = entry.build();

    // Should contain escaped characters
    EXPECT_NE(result.find("\\\""), std::string::npos);
    EXPECT_NE(result.find("\\\\"), std::string::npos);
}

TEST_F(LoggerTest, JsonEscapingNewlineAndTab) {
    LogEntry entry("Line1\nLine2\tTabbed\rCarriage");
    std::string result = entry.build();

    // Should contain escaped newline, tab, and carriage return
    EXPECT_NE(result.find("\\n"), std::string::npos);
    EXPECT_NE(result.find("\\t"), std::string::npos);
    EXPECT_NE(result.find("\\r"), std::string::npos);
}

// =============================================================================
// Logger initialization edge cases
// =============================================================================

/**
 * @brief Test double initialization is a no-op.
 */
TEST(LoggerInitTest, DoubleInitialization) {
    // First init
    Logger::init("info");
    EXPECT_TRUE(Logger::is_initialized());

    auto* logger1 = Logger::get();

    // Second init should be no-op
    Logger::init("debug");
    EXPECT_TRUE(Logger::is_initialized());

    auto* logger2 = Logger::get();

    // Should be the same logger instance
    EXPECT_EQ(logger1, logger2);

    Logger::shutdown();
}

/**
 * @brief Test "warning" alias for log level.
 */
TEST(LoggerInitTest, WarningLevelAlias) {
    // "warning" should work as alias for "warn"
    Logger::init("warning");
    EXPECT_TRUE(Logger::is_initialized());
    EXPECT_NE(Logger::get(), nullptr);
    Logger::shutdown();
}

/**
 * @brief Test unknown log level defaults to info.
 */
TEST(LoggerInitTest, UnknownLevelDefaultsToInfo) {
    Logger::init("unknown_level");
    EXPECT_TRUE(Logger::is_initialized());
    EXPECT_NE(Logger::get(), nullptr);
    Logger::shutdown();
}

/**
 * @brief Test all valid log levels.
 */
TEST(LoggerInitTest, AllValidLogLevels) {
    std::vector<std::string> levels = {"trace", "debug", "info", "warn", "warning", "error"};

    for (const auto& level : levels) {
        Logger::init(level);
        EXPECT_TRUE(Logger::is_initialized()) << "Failed for level: " << level;
        EXPECT_NE(Logger::get(), nullptr) << "Failed for level: " << level;
        Logger::shutdown();
    }
}

/**
 * @brief Test Logger::get() returns nullptr before initialization.
 */
TEST(LoggerInitTest, GetBeforeInit) {
    // Ensure clean state
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }

    EXPECT_FALSE(Logger::is_initialized());
    EXPECT_EQ(Logger::get(), nullptr);
}

/**
 * @brief Test shutdown can be called multiple times safely.
 */
TEST(LoggerInitTest, DoubleShutdown) {
    Logger::init("info");
    EXPECT_TRUE(Logger::is_initialized());

    Logger::shutdown();
    EXPECT_FALSE(Logger::is_initialized());

    // Second shutdown should be safe
    Logger::shutdown();
    EXPECT_FALSE(Logger::is_initialized());
}

/**
 * @brief Test log_trace with trace-level logger (covers L126).
 */
TEST(LoggerInitTest, LogTraceWithTraceLevel) {
    Logger::init("trace");
    EXPECT_TRUE(Logger::is_initialized());

    // This should execute the LOG_TRACE_L1 macro body
    Logger::log_trace(LogEntry("Trace message with trace level").component("test"));

    Logger::shutdown();
}

/**
 * @brief Test log_warn with initialized logger (covers L144).
 */
TEST(LoggerInitTest, LogWarnWithInitializedLogger) {
    Logger::init("warn");
    EXPECT_TRUE(Logger::is_initialized());

    // This should execute the QUILL_LOG_WARNING macro body
    Logger::log_warn(LogEntry("Warning message").component("test"));

    Logger::shutdown();
}

/**
 * @brief Test all structured log methods with initialized logger.
 */
TEST(LoggerInitTest, AllStructuredLogMethodsInitialized) {
    Logger::init("trace");  // Lowest level to ensure all messages pass
    EXPECT_TRUE(Logger::is_initialized());

    // Exercise all log methods with initialized logger
    Logger::log_trace(LogEntry("Trace").component("test"));
    Logger::log_debug(LogEntry("Debug").component("test"));
    Logger::log_info(LogEntry("Info").component("test"));
    Logger::log_warn(LogEntry("Warn").component("test"));
    Logger::log_error(LogEntry("Error").component("test"));

    Logger::shutdown();
}

// =============================================================================
// LogEntry with all domain fields
// =============================================================================

TEST_F(LoggerTest, LogEntryWithAllDomainFields) {
    DomainContext domain{
        .camera_id = "cam-01",
        .sensor_id = "sensor-xyz",
        .scene_id = "scene-main",
        .object_category = "person",
        .track_uuid = "uuid-12345"
    };
    LogEntry entry("Full domain context");

    std::string result = entry.domain(domain).build();

    EXPECT_NE(result.find("domain"), std::string::npos);
    EXPECT_NE(result.find("cam-01"), std::string::npos);
    EXPECT_NE(result.find("sensor-xyz"), std::string::npos);
    EXPECT_NE(result.find("scene-main"), std::string::npos);
    EXPECT_NE(result.find("person"), std::string::npos);
    EXPECT_NE(result.find("uuid-12345"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryWithPartialDomainFields) {
    // Only sensor_id and track_uuid set
    DomainContext domain{
        .sensor_id = "sensor-only",
        .track_uuid = "track-only"
    };
    LogEntry entry("Partial domain");

    std::string result = entry.domain(domain).build();

    EXPECT_NE(result.find("sensor_id"), std::string::npos);
    EXPECT_NE(result.find("sensor-only"), std::string::npos);
    EXPECT_NE(result.find("track_uuid"), std::string::npos);
    EXPECT_NE(result.find("track-only"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryWithMqttNoMessageId) {
    MqttContext mqtt{"topic/path", std::nullopt, "subscribe"};
    LogEntry entry("MQTT without message ID");

    std::string result = entry.mqtt(mqtt).build();

    EXPECT_NE(result.find("mqtt"), std::string::npos);
    EXPECT_NE(result.find("topic/path"), std::string::npos);
    EXPECT_NE(result.find("subscribe"), std::string::npos);
    // message_id should not appear when nullopt
    EXPECT_EQ(result.find("message_id"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryWithAllContexts) {
    LogEntry entry("Full context message");

    std::string result = entry
        .component("tracker")
        .operation("process")
        .trace({"trace-abc", "span-def"})
        .mqtt({"topic/test", 999, "publish"})
        .domain({.camera_id = "cam-1", .scene_id = "scene-1"})
        .error({"ValidationError", "Invalid input"})
        .build();

    EXPECT_NE(result.find("component"), std::string::npos);
    EXPECT_NE(result.find("operation"), std::string::npos);
    EXPECT_NE(result.find("trace_id"), std::string::npos);
    EXPECT_NE(result.find("mqtt"), std::string::npos);
    EXPECT_NE(result.find("domain"), std::string::npos);
    EXPECT_NE(result.find("error"), std::string::npos);
}

TEST_F(LoggerTest, LogEntryPlainMessageOnly) {
    LogEntry entry("Simple message without context");
    std::string result = entry.build();

    // Should just be the escaped message
    EXPECT_NE(result.find("Simple message"), std::string::npos);
    // Should not have any context fields
    EXPECT_EQ(result.find("component"), std::string::npos);
    EXPECT_EQ(result.find("mqtt"), std::string::npos);
    EXPECT_EQ(result.find("domain"), std::string::npos);
}

// =============================================================================
// Null logger branch coverage (log methods when logger not initialized)
// =============================================================================

/**
 * @brief Test log_trace with null logger (not initialized).
 */
TEST(LoggerNullTest, LogTraceWithNullLogger) {
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }
    EXPECT_EQ(Logger::get(), nullptr);

    // Should not crash - just silently returns
    Logger::log_trace(LogEntry("Test trace"));
    SUCCEED();
}

/**
 * @brief Test log_debug with null logger.
 */
TEST(LoggerNullTest, LogDebugWithNullLogger) {
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }
    Logger::log_debug(LogEntry("Test debug"));
    SUCCEED();
}

/**
 * @brief Test log_info with null logger.
 */
TEST(LoggerNullTest, LogInfoWithNullLogger) {
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }
    Logger::log_info(LogEntry("Test info"));
    SUCCEED();
}

/**
 * @brief Test log_warn with null logger.
 */
TEST(LoggerNullTest, LogWarnWithNullLogger) {
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }
    Logger::log_warn(LogEntry("Test warn"));
    SUCCEED();
}

/**
 * @brief Test log_error with null logger.
 */
TEST(LoggerNullTest, LogErrorWithNullLogger) {
    if (Logger::is_initialized()) {
        Logger::shutdown();
    }
    Logger::log_error(LogEntry("Test error"));
    SUCCEED();
}

} // namespace
} // namespace tracker
