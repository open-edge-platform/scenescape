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

} // namespace
} // namespace tracker
