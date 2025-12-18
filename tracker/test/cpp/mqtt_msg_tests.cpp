#include <gtest/gtest.h>
#include <chrono>
#include <format>
#include <string>
#include "time_utils.h"

static std::string format_rfc3339_ms(std::chrono::system_clock::time_point tp) {
    auto tp_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(tp);
    return std::format("{:%FT%T}", tp_ms) + "Z";
}

TEST(MqttMsgTimestamp, RoundTripMilliseconds) {
    std::string s = "2025-12-18T13:13:24.835Z";
    auto tp = parse_timestamp(s);
    auto out = format_rfc3339_ms(tp);
    EXPECT_EQ(out, s);
}

TEST(MqttMsgTimestamp, MissingZThrows) {
    std::string s = "2025-12-18T13:13:24.835"; // no Z
    EXPECT_THROW({ (void)parse_timestamp(s); }, std::runtime_error);
}

TEST(MqttMsgTimestamp, MissingMillisThrows) {
    std::string s = "2025-12-18T13:13:24Z"; // no .mmm
    EXPECT_THROW({ (void)parse_timestamp(s); }, std::runtime_error);
}

TEST(MqttMsgTimestamp, WrongMillisLengthThrows) {
    EXPECT_THROW({ (void)parse_timestamp("2025-12-18T13:13:24.83Z"); }, std::runtime_error);   // 2 digits
    EXPECT_THROW({ (void)parse_timestamp("2025-12-18T13:13:24.8351Z"); }, std::runtime_error); // 4 digits
}

TEST(MqttMsgTimestamp, NonDigitMillisThrows) {
    EXPECT_THROW({ (void)parse_timestamp("2025-12-18T13:13:24.abZ"); }, std::runtime_error);
}
