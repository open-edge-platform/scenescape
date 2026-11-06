// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "z_reference.hpp"

#include <gtest/gtest.h>

#include <rv/tracking/TrackedObject.hpp>

#include <vector>

namespace tracker {
namespace {

rv::tracking::TrackedObject makeObject(double z, double height, bool z_measured) {
    rv::tracking::TrackedObject object;
    object.z = z;
    object.height = height;
    object.zMeasured = z_measured;
    return object;
}

TEST(ZReferenceTest, ToCentreOfMassRaisesUnmeasuredZByHalfHeight) {
    std::vector<std::vector<rv::tracking::TrackedObject>> objects_per_camera = {
        {makeObject(0.0, 1.7, false), makeObject(0.3, 1.0, false)},
        {makeObject(0.0, 1.7, false)},
    };

    toCentreOfMass(objects_per_camera);

    EXPECT_DOUBLE_EQ(objects_per_camera[0][0].z, 0.85);
    EXPECT_DOUBLE_EQ(objects_per_camera[0][1].z, 0.8) << "hover z keeps its offset";
    EXPECT_DOUBLE_EQ(objects_per_camera[1][0].z, 0.85) << "every camera is converted";
    EXPECT_FALSE(objects_per_camera[0][0].zMeasured);
}

TEST(ZReferenceTest, ToCentreOfMassKeepsMeasuredZ) {
    std::vector<std::vector<rv::tracking::TrackedObject>> objects_per_camera = {
        {makeObject(0.9, 1.8, true)}};

    toCentreOfMass(objects_per_camera);

    EXPECT_EQ(objects_per_camera[0][0].z, 0.9);
}

TEST(ZReferenceTest, ToCentreOfMassKeepsZOfZeroHeight) {
    std::vector<std::vector<rv::tracking::TrackedObject>> objects_per_camera = {
        {makeObject(0.4, 0.0, false)}};

    toCentreOfMass(objects_per_camera);

    EXPECT_EQ(objects_per_camera[0][0].z, 0.4);
}

TEST(ZReferenceTest, FootprintBaseZLowersByHalfHeight) {
    EXPECT_DOUBLE_EQ(footprintBaseZ(makeObject(0.85, 1.7, true)), 0.0);
    EXPECT_DOUBLE_EQ(footprintBaseZ(makeObject(2.0, 1.0, false)), 1.5);
    EXPECT_EQ(footprintBaseZ(makeObject(0.4, 0.0, false)), 0.4);
}

TEST(ZReferenceTest, FootprintBaseZInvertsToCentreOfMass) {
    std::vector<std::vector<rv::tracking::TrackedObject>> objects_per_camera = {
        {makeObject(0.3, 1.7, false)}};

    toCentreOfMass(objects_per_camera);

    EXPECT_DOUBLE_EQ(footprintBaseZ(objects_per_camera[0][0]), 0.3);
}

} // namespace
} // namespace tracker
