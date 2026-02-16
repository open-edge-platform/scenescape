// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include "id_map.hpp"

namespace tracker {
namespace {

/// Deterministic generator that produces sequential UUID-like strings.
class SequentialGenerator {
public:
    std::string operator()() {
        static constexpr std::array kUuids = {
            "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
            "c3d4e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f",
        };
        return kUuids.at(counter_++);
    }

private:
    int counter_ = 0;
};

TEST(IdMapTest, EmptyOldMapGeneratesNewUuids) {
    std::unordered_map<int32_t, std::string> old_map;
    std::vector<int32_t> active_ids = {10, 20, 30};
    SequentialGenerator gen;

    auto result = update_id_map(old_map, active_ids, std::ref(gen));

    ASSERT_EQ(result.size(), 3u);
    EXPECT_EQ(result.at(10), "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d");
    EXPECT_EQ(result.at(20), "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e");
    EXPECT_EQ(result.at(30), "c3d4e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f");
}

TEST(IdMapTest, PreservesExistingUuids) {
    std::unordered_map<int32_t, std::string> old_map = {
        {1, "d4e5f6a7-b8c9-4d0e-8f1a-2b3c4d5e6f7a"},
        {2, "e5f6a7b8-c9d0-4e1f-8a2b-3c4d5e6f7a8b"},
    };
    std::vector<int32_t> active_ids = {1, 2};
    SequentialGenerator gen;

    auto result = update_id_map(old_map, active_ids, std::ref(gen));

    ASSERT_EQ(result.size(), 2u);
    EXPECT_EQ(result.at(1), "d4e5f6a7-b8c9-4d0e-8f1a-2b3c4d5e6f7a");
    EXPECT_EQ(result.at(2), "e5f6a7b8-c9d0-4e1f-8a2b-3c4d5e6f7a8b");
}

TEST(IdMapTest, MixOfExistingAndNewIds) {
    std::unordered_map<int32_t, std::string> old_map = {
        {1, "f6a7b8c9-d0e1-4f2a-8b3c-4d5e6f7a8b9c"},
    };
    std::vector<int32_t> active_ids = {1, 2, 3};
    SequentialGenerator gen;

    auto result = update_id_map(old_map, active_ids, std::ref(gen));

    ASSERT_EQ(result.size(), 3u);
    EXPECT_EQ(result.at(1), "f6a7b8c9-d0e1-4f2a-8b3c-4d5e6f7a8b9c"); // preserved
    EXPECT_EQ(result.at(2), "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"); // new
    EXPECT_EQ(result.at(3), "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"); // new
}

TEST(IdMapTest, DropsStaleEntries) {
    std::unordered_map<int32_t, std::string> old_map = {
        {1, "a7b8c9d0-e1f2-4a3b-8c4d-5e6f7a8b9c0d"},
        {2, "b8c9d0e1-f2a3-4b4c-8d5e-6f7a8b9c0d1e"},
        {3, "c9d0e1f2-a3b4-4c5d-8e6f-7a8b9c0d1e2f"},
    };
    std::vector<int32_t> active_ids = {2}; // 1 and 3 are stale

    auto result = update_id_map(old_map, active_ids);

    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result.at(2), "b8c9d0e1-f2a3-4b4c-8d5e-6f7a8b9c0d1e");
    EXPECT_EQ(result.count(1), 0u);
    EXPECT_EQ(result.count(3), 0u);
}

TEST(IdMapTest, EmptyActiveIdsReturnsEmptyMap) {
    std::unordered_map<int32_t, std::string> old_map = {
        {1, "d0e1f2a3-b4c5-4d6e-8f7a-8b9c0d1e2f3a"}};
    std::vector<int32_t> active_ids;

    auto result = update_id_map(old_map, active_ids);

    EXPECT_TRUE(result.empty());
}

TEST(IdMapTest, BothEmpty) {
    std::unordered_map<int32_t, std::string> old_map;
    std::vector<int32_t> active_ids;

    auto result = update_id_map(old_map, active_ids);

    EXPECT_TRUE(result.empty());
}

TEST(IdMapTest, DuplicateActiveIdsDeduplicates) {
    std::unordered_map<int32_t, std::string> old_map;
    std::vector<int32_t> active_ids = {5, 5, 5};
    SequentialGenerator gen;

    auto result = update_id_map(old_map, active_ids, std::ref(gen));

    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result.at(5), "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"); // only first call used
}

TEST(IdMapTest, DefaultGeneratorProducesValidUuids) {
    std::unordered_map<int32_t, std::string> old_map;
    std::vector<int32_t> active_ids = {42};

    auto result = update_id_map(old_map, active_ids); // default generate_uuid_v4

    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result.at(42).size(), 36u);
}

TEST(IdMapTest, GeneratorNotCalledForExistingIds) {
    std::unordered_map<int32_t, std::string> old_map = {
        {1, "e1f2a3b4-c5d6-4e7f-8a8b-9c0d1e2f3a4b"}};
    std::vector<int32_t> active_ids = {1};
    int call_count = 0;
    auto counting_gen = [&]() -> std::string {
        ++call_count;
        return "should-not-appear";
    };

    auto result = update_id_map(old_map, active_ids, counting_gen);

    EXPECT_EQ(call_count, 0);
    EXPECT_EQ(result.at(1), "e1f2a3b4-c5d6-4e7f-8a8b-9c0d1e2f3a4b");
}

} // namespace
} // namespace tracker
