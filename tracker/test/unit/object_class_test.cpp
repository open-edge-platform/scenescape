// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "object_class.hpp"

#include <gtest/gtest.h>

using namespace tracker;

TEST(ObjectClassTest, ParseManagerListPayload) {
    const auto map = parseObjectClassesFromAssetsJson(R"({
        "count": 2,
        "results": [
            {"name": "person", "shift_type": 1, "x_size": 0.5, "y_size": 0.5},
            {"name": "FW190D", "shift_type": 2, "x_size": 1.0, "y_size": 1.0}
        ]
    })");

    ASSERT_EQ(map.size(), 2u);

    const auto person = lookupObjectClass(map, "Person");
    EXPECT_EQ(person.shift_type, ObjectClassConfig::kShiftType1);
    ASSERT_TRUE(person.footprint_half_m.has_value());
    EXPECT_DOUBLE_EQ(*person.footprint_half_m, 0.25);

    const auto plane = lookupObjectClass(map, "FW190D");
    EXPECT_EQ(plane.shift_type, ObjectClassConfig::kShiftType2);
    ASSERT_TRUE(plane.footprint_half_m.has_value());
    EXPECT_DOUBLE_EQ(*plane.footprint_half_m, 0.5);
}

TEST(ObjectClassTest, UnknownCategoryDefaultsToType1) {
    ObjectClassMap empty;
    const auto cfg = lookupObjectClass(empty, "vehicle");
    EXPECT_EQ(cfg.shift_type, ObjectClassConfig::kShiftType1);
    EXPECT_FALSE(cfg.footprint_half_m.has_value());
}

TEST(ObjectClassTest, ZeroSizesOmitFixedFootprint) {
    const auto map = parseObjectClassesFromAssetsJson(
        R"({"results":[{"name":"thing","shift_type":1,"x_size":0,"y_size":0}]})");
    const auto cfg = lookupObjectClass(map, "thing");
    EXPECT_EQ(cfg.shift_type, ObjectClassConfig::kShiftType1);
    EXPECT_FALSE(cfg.footprint_half_m.has_value());
}

TEST(ObjectClassTest, SkipsNamelessEntries) {
    const auto map = parseObjectClassesFromAssetsJson(
        R"({"results":[{"shift_type":2},{"name":"car","shift_type":2,"x_size":2,"y_size":4}]})");
    ASSERT_EQ(map.size(), 1u);
    EXPECT_TRUE(map.contains("car"));
}
