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

    const auto person = lookupObjectClass(map, "person");
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

TEST(ObjectClassTest, CategoryMatchIsCaseSensitive) {
    const auto map = parseObjectClassesFromAssetsJson(
        R"({"results":[{"name":"Plane","shift_type":2},{"name":"plane","shift_type":1}]})");
    ASSERT_EQ(map.size(), 2u);
    EXPECT_EQ(lookupObjectClass(map, "Plane").shift_type, ObjectClassConfig::kShiftType2);
    EXPECT_EQ(lookupObjectClass(map, "plane").shift_type, ObjectClassConfig::kShiftType1);
    EXPECT_FALSE(lookupObjectClass(map, "PLANE").footprint_half_m.has_value());
}

TEST(ObjectClassTest, ZeroSizesKeepFixedFootprint) {
    const auto map = parseObjectClassesFromAssetsJson(
        R"({"results":[{"name":"flat","x_size":0,"y_size":0},{"name":"thin","x_size":0,"y_size":2}]})");
    const auto flat = lookupObjectClass(map, "flat");
    ASSERT_TRUE(flat.footprint_half_m.has_value());
    EXPECT_DOUBLE_EQ(*flat.footprint_half_m, 0.0);
    const auto thin = lookupObjectClass(map, "thin");
    ASSERT_TRUE(thin.footprint_half_m.has_value());
    EXPECT_DOUBLE_EQ(*thin.footprint_half_m, 0.5);
}

TEST(ObjectClassTest, MissingOrNonNumericSizesUseDefaultEdgeLength) {
    const auto map =
        parseObjectClassesFromAssetsJson(R"({"results":[{"name":"thing","x_size":"big"}]})");
    const auto cfg = lookupObjectClass(map, "thing");
    ASSERT_TRUE(cfg.footprint_half_m.has_value());
    EXPECT_DOUBLE_EQ(*cfg.footprint_half_m, 0.5);
}

TEST(ObjectClassTest, ShiftTypeMatchesControllerEquality) {
    const auto map = parseObjectClassesFromAssetsJson(R"({"results":[
        {"name":"float2","shift_type":2.0},
        {"name":"three","shift_type":3},
        {"name":"string2","shift_type":"2"},
        {"name":"null","shift_type":null}
    ]})");
    EXPECT_EQ(lookupObjectClass(map, "float2").shift_type, ObjectClassConfig::kShiftType2);
    EXPECT_EQ(lookupObjectClass(map, "three").shift_type, ObjectClassConfig::kShiftType1);
    EXPECT_EQ(lookupObjectClass(map, "string2").shift_type, ObjectClassConfig::kShiftType1);
    EXPECT_EQ(lookupObjectClass(map, "null").shift_type, ObjectClassConfig::kShiftType1);
}

TEST(ObjectClassTest, SkipsNamelessEntries) {
    const auto map = parseObjectClassesFromAssetsJson(
        R"({"results":[{"shift_type":2},{"name":"car","shift_type":2,"x_size":2,"y_size":4}]})");
    ASSERT_EQ(map.size(), 1u);
    EXPECT_TRUE(map.contains("car"));
}
