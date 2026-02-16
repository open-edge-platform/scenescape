// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include "uuid.hpp"

#include <set>

#include <uuid.h> // stduuid library — independent UUID validator

namespace tracker {
namespace {

// =============================================================================
// Format tests (validated against stduuid library)
// =============================================================================

TEST(UuidTest, GeneratesValidUuid) {
    auto uuid_str = generate_uuid_v4();
    auto parsed = uuids::uuid::from_string(uuid_str);
    ASSERT_TRUE(parsed.has_value()) << "stduuid failed to parse: " << uuid_str;
    EXPECT_FALSE(parsed->is_nil()) << "UUID should not be nil: " << uuid_str;
}

TEST(UuidTest, GeneratesVersion4) {
    auto uuid_str = generate_uuid_v4();
    auto parsed = uuids::uuid::from_string(uuid_str);
    ASSERT_TRUE(parsed.has_value()) << "stduuid failed to parse: " << uuid_str;
    EXPECT_EQ(parsed->version(), uuids::uuid_version::random_number_based)
        << "UUID should be version 4 (random): " << uuid_str;
}

TEST(UuidTest, HasCorrectVariant) {
    auto uuid_str = generate_uuid_v4();
    auto parsed = uuids::uuid::from_string(uuid_str);
    ASSERT_TRUE(parsed.has_value()) << "stduuid failed to parse: " << uuid_str;
    EXPECT_EQ(parsed->variant(), uuids::uuid_variant::rfc)
        << "UUID should have RFC 4122 variant: " << uuid_str;
}

TEST(UuidTest, HasCorrectLength) {
    auto uuid_str = generate_uuid_v4();
    EXPECT_EQ(uuid_str.size(), 36u) << "UUID should be 36 characters: " << uuid_str;
}

TEST(UuidTest, UsesLowercaseHex) {
    auto uuid_str = generate_uuid_v4();
    for (size_t i = 0; i < uuid_str.size(); ++i) {
        if (uuid_str[i] == '-')
            continue;
        EXPECT_TRUE((uuid_str[i] >= '0' && uuid_str[i] <= '9') ||
                    (uuid_str[i] >= 'a' && uuid_str[i] <= 'f'))
            << "Non-lowercase hex at position " << i << ": " << uuid_str;
    }
}

TEST(UuidTest, HyphensAtCorrectPositions) {
    auto uuid_str = generate_uuid_v4();
    EXPECT_EQ(uuid_str[8], '-');
    EXPECT_EQ(uuid_str[13], '-');
    EXPECT_EQ(uuid_str[18], '-');
    EXPECT_EQ(uuid_str[23], '-');
}

// =============================================================================
// Uniqueness tests
// =============================================================================

TEST(UuidTest, GeneratesUniqueValues) {
    constexpr int kCount = 1000;
    std::set<std::string> uuids;
    for (int i = 0; i < kCount; ++i) {
        uuids.insert(generate_uuid_v4());
    }
    EXPECT_EQ(uuids.size(), kCount) << "All generated UUIDs should be unique";
}

TEST(UuidTest, ConsecutiveCallsProduceDifferentValues) {
    auto uuid1 = generate_uuid_v4();
    auto uuid2 = generate_uuid_v4();
    EXPECT_NE(uuid1, uuid2);
}

// =============================================================================
// Consistency tests
// =============================================================================

TEST(UuidTest, MultipleCallsAllValid) {
    // Verify every generated UUID passes stduuid validation
    for (int i = 0; i < 100; ++i) {
        auto uuid_str = generate_uuid_v4();
        auto parsed = uuids::uuid::from_string(uuid_str);
        ASSERT_TRUE(parsed.has_value()) << "UUID #" << i << " failed stduuid parse: " << uuid_str;
        EXPECT_EQ(parsed->version(), uuids::uuid_version::random_number_based)
            << "UUID #" << i << " wrong version: " << uuid_str;
        EXPECT_EQ(parsed->variant(), uuids::uuid_variant::rfc)
            << "UUID #" << i << " wrong variant: " << uuid_str;
    }
}

} // namespace
} // namespace tracker
