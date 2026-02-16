// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include "time_utils.hpp"

#include <chrono>
#include <string>

namespace tracker {
namespace {

using namespace std::chrono;

/**
 * @brief Helper to build a known UTC time_point for test assertions.
 */
sys_time<milliseconds> make_utc(int y, unsigned m, unsigned d, int h, int min, int s, int ms = 0) {
    auto ymd = year{y} / month{m} / day{d};
    return sys_days{ymd} + hours{h} + minutes{min} + seconds{s} + milliseconds{ms};
}

//
// Parameterized tests for valid timestamps
//
struct ValidTimestampTestCase {
    std::string name;
    std::string input;
    sys_time<milliseconds> expected;
};

void PrintTo(const ValidTimestampTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class ValidTimestampTest : public ::testing::TestWithParam<ValidTimestampTestCase> {};

TEST_P(ValidTimestampTest, ParsesCorrectly) {
    const auto& tc = GetParam();
    auto result = parseTimestamp(tc.input);
    ASSERT_TRUE(result.has_value()) << "Failed to parse: " << tc.input;
    EXPECT_EQ(*result, tc.expected) << "Mismatch for: " << tc.input;
}

INSTANTIATE_TEST_SUITE_P(
    ValidTimestamps, ValidTimestampTest,
    ::testing::Values(ValidTimestampTestCase{"StandardWithMillis", "2026-01-27T12:00:00.482Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 482)},
                      ValidTimestampTestCase{"ZeroMillis", "2026-01-27T12:00:00.000Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 0)},
                      ValidTimestampTestCase{"NoFractionalSeconds", "2026-01-27T12:00:00Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 0)},
                      ValidTimestampTestCase{"OneDigitFraction", "2026-01-27T12:00:00.1Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 100)},
                      ValidTimestampTestCase{"TwoDigitFraction", "2026-01-27T12:00:00.12Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 120)},
                      ValidTimestampTestCase{"ThreeDigitFraction", "2026-01-27T12:00:00.123Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 123)},
                      ValidTimestampTestCase{"Midnight", "2026-01-01T00:00:00.000Z",
                                             make_utc(2026, 1, 1, 0, 0, 0, 0)},
                      ValidTimestampTestCase{"EndOfDay", "2026-12-31T23:59:59.999Z",
                                             make_utc(2026, 12, 31, 23, 59, 59, 999)},
                      ValidTimestampTestCase{"LeapYear", "2024-02-29T12:00:00.000Z",
                                             make_utc(2024, 2, 29, 12, 0, 0, 0)},
                      ValidTimestampTestCase{"Epoch", "1970-01-01T00:00:00.000Z",
                                             make_utc(1970, 1, 1, 0, 0, 0, 0)}),
    [](const ::testing::TestParamInfo<ValidTimestampTestCase>& info) { return info.param.name; });

//
// Parameterized tests for invalid timestamps
//
struct InvalidTimestampTestCase {
    std::string name;
    std::string input;
};

void PrintTo(const InvalidTimestampTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class InvalidTimestampTest : public ::testing::TestWithParam<InvalidTimestampTestCase> {};

TEST_P(InvalidTimestampTest, ReturnsNullopt) {
    const auto& tc = GetParam();
    auto result = parseTimestamp(tc.input);
    EXPECT_FALSE(result.has_value()) << "Expected failure for: " << tc.input;
}

INSTANTIATE_TEST_SUITE_P(
    InvalidTimestamps, InvalidTimestampTest,
    ::testing::Values(InvalidTimestampTestCase{"Empty", ""},
                      InvalidTimestampTestCase{"Garbage", "not-a-timestamp"},
                      InvalidTimestampTestCase{"MissingZ", "2026-01-27T12:00:00.000"},
                      InvalidTimestampTestCase{"SpaceSeparator", "2026-01-27 12:00:00.000Z"},
                      InvalidTimestampTestCase{"DateOnly", "2026-01-27"},
                      InvalidTimestampTestCase{"InvalidMonth", "2026-13-01T12:00:00Z"},
                      InvalidTimestampTestCase{"InvalidDay", "2026-02-30T12:00:00Z"},
                      InvalidTimestampTestCase{"InvalidHour", "2026-01-27T25:00:00Z"},
                      InvalidTimestampTestCase{"NonLeapYear", "2025-02-29T12:00:00Z"},
                      InvalidTimestampTestCase{"TrailingJunk", "2026-01-27T12:00:00.000Zextra"}),
    [](const ::testing::TestParamInfo<InvalidTimestampTestCase>& info) { return info.param.name; });

//
// Round-trip consistency: parse then format should reproduce input
//
TEST(TimestampRoundTrip, CanonicalFormat) {
    const std::string input = "2026-06-15T08:30:45.123Z";
    auto result = parseTimestamp(input);
    ASSERT_TRUE(result.has_value());

    // Round-trip through formatTimestamp
    auto formatted = formatTimestamp(*result);
    EXPECT_EQ(formatted, input);
}

//
// formatTimestamp tests
//
TEST(FormatTimestamp, ProducesIso8601WithMillis) {
    using namespace std::chrono;
    auto tp = sys_days{2026y / January / 1} + 0h + 0min + 0s;
    EXPECT_EQ(formatTimestamp(tp), "2026-01-01T00:00:00.000Z");
}

TEST(FormatTimestamp, PreservesMilliseconds) {
    using namespace std::chrono;
    auto tp = sys_days{2026y / March / 15} + 14h + 30min + 45s + 789ms;
    EXPECT_EQ(formatTimestamp(tp), "2026-03-15T14:30:45.789Z");
}

} // namespace
} // namespace tracker
