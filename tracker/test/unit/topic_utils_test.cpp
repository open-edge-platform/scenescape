// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include "topic_utils.hpp"

#include <string>

namespace tracker {
namespace {

//
// Parameterized tests for valid topic segments
//
struct ValidSegmentTestCase {
    std::string name;
    std::string segment;
};

void PrintTo(const ValidSegmentTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class ValidTopicSegmentTest : public ::testing::TestWithParam<ValidSegmentTestCase> {};

TEST_P(ValidTopicSegmentTest, AcceptsValidSegment) {
    const auto& tc = GetParam();
    EXPECT_TRUE(isValidTopicSegment(tc.segment)) << "Expected '" << tc.segment << "' to be valid";
}

INSTANTIATE_TEST_SUITE_P(
    ValidSegments, ValidTopicSegmentTest,
    ::testing::Values(ValidSegmentTestCase{"Alphanumeric", "cam1"},
                      ValidSegmentTestCase{"WithHyphen", "camera-1"},
                      ValidSegmentTestCase{"WithUnderscore", "camera_1"},
                      ValidSegmentTestCase{"WithDot", "camera.1"},
                      ValidSegmentTestCase{"UUID", "550e8400-e29b-41d4-a716-446655440000"},
                      ValidSegmentTestCase{"MixedCase", "TestCamera1"},
                      ValidSegmentTestCase{"AllAllowedChars", "Cam-1_test.data"},
                      ValidSegmentTestCase{"SingleChar", "x"},
                      ValidSegmentTestCase{"NumericOnly", "12345"}),
    [](const ::testing::TestParamInfo<ValidSegmentTestCase>& info) { return info.param.name; });

//
// Parameterized tests for invalid topic segments
//
struct InvalidSegmentTestCase {
    std::string name;
    std::string segment;
};

void PrintTo(const InvalidSegmentTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class InvalidTopicSegmentTest : public ::testing::TestWithParam<InvalidSegmentTestCase> {};

TEST_P(InvalidTopicSegmentTest, RejectsInvalidSegment) {
    const auto& tc = GetParam();
    EXPECT_FALSE(isValidTopicSegment(tc.segment))
        << "Expected '" << tc.segment << "' to be rejected";
}

INSTANTIATE_TEST_SUITE_P(
    InvalidSegments, InvalidTopicSegmentTest,
    ::testing::Values(
        InvalidSegmentTestCase{"Empty", ""}, InvalidSegmentTestCase{"Slash", "cam/1"},
        InvalidSegmentTestCase{"Plus", "cam+1"}, InvalidSegmentTestCase{"Hash", "cam#1"},
        InvalidSegmentTestCase{"Dollar", "cam$1"}, InvalidSegmentTestCase{"Space", "cam 1"},
        InvalidSegmentTestCase{"Tab", "cam\t1"}, InvalidSegmentTestCase{"Newline", "cam\n1"},
        InvalidSegmentTestCase{"NullByte", std::string("cam\0id", 6)},
        InvalidSegmentTestCase{"LeadingSlash", "/cam1"},
        InvalidSegmentTestCase{"TrailingSlash", "cam1/"},
        InvalidSegmentTestCase{"MultipleSlashes", "scene/cam/1"},
        InvalidSegmentTestCase{"Asterisk", "cam*1"}, InvalidSegmentTestCase{"AtSign", "cam@1"},
        InvalidSegmentTestCase{"Colon", "cam:1"}, InvalidSegmentTestCase{"Semicolon", "cam;1"},
        InvalidSegmentTestCase{"Backslash", "cam\\1"}, InvalidSegmentTestCase{"Quote", "cam\"1"},
        InvalidSegmentTestCase{"SingleQuote", "cam'1"}),
    [](const ::testing::TestParamInfo<InvalidSegmentTestCase>& info) { return info.param.name; });

} // namespace
} // namespace tracker
