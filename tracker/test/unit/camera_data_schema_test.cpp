// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "utils/json_schema_validator.hpp"

#include <gtest/gtest.h>

#include <string>

namespace tracker {
namespace {

struct CameraDataSchemaTestCase {
    std::string name;
    std::string detection;
    bool valid;
};

class CameraDataSchemaTest : public ::testing::TestWithParam<CameraDataSchemaTestCase> {};

TEST_P(CameraDataSchemaTest, ValidatesDetectionWithRapidJson) {
    const auto& test_case = GetParam();
    test::JsonSchemaValidator validator(test::get_schema_path("camera-data.schema.json"));
    const std::string payload =
        R"({"id":"cam1","timestamp":"2026-10-23T07:00:00Z","objects":{"person":[)" +
        test_case.detection + "]}}";

    EXPECT_EQ(validator.validate(payload), test_case.valid) << validator.get_error();
}

INSTANTIATE_TEST_SUITE_P(
    DetectionConstraints, CameraDataSchemaTest,
    ::testing::Values(
        CameraDataSchemaTestCase{
            "ValidBoundingBox",
            R"({"bounding_box_px":{"x":-1,"y":0,"width":0,"height":1},"confidence":1})", true},
        CameraDataSchemaTestCase{
            "ValidSensorFrameGeometry",
            R"({"translation":[-1,0,1],"size":[0.001,1,2],"rotation":[0,0,0,1]})", true},
        CameraDataSchemaTestCase{"MissingGeometry", R"({})", false},
        CameraDataSchemaTestCase{
            "AmbiguousGeometry",
            R"({"bounding_box_px":{"x":0,"y":0,"width":1,"height":1},"translation":[0,0,0],"size":[1,1,1]})",
            false},
        CameraDataSchemaTestCase{
            "BoundingBoxWithPartialGeometry",
            R"({"bounding_box_px":{"x":0,"y":0,"width":1,"height":1},"size":[1,1,1]})", false},
        CameraDataSchemaTestCase{"MissingBoundingBoxHeight",
                                 R"({"bounding_box_px":{"x":0,"y":0,"width":1}})", false},
        CameraDataSchemaTestCase{"NonNumericBoundingBox",
                                 R"({"bounding_box_px":{"x":"bad","y":0,"width":1,"height":1}})",
                                 false},
        CameraDataSchemaTestCase{"NegativeBoundingBoxWidth",
                                 R"({"bounding_box_px":{"x":0,"y":0,"width":-1,"height":1}})",
                                 false},
        CameraDataSchemaTestCase{
            "OutOfRangeConfidence",
            R"({"bounding_box_px":{"x":0,"y":0,"width":1,"height":1},"confidence":2})", false},
        CameraDataSchemaTestCase{
            "NegativeDetectionId",
            R"({"id":-1,"bounding_box_px":{"x":0,"y":0,"width":1,"height":1}})", false},
        CameraDataSchemaTestCase{"ZeroSizeX", R"({"translation":[0,0,0],"size":[0,1,1]})", false},
        CameraDataSchemaTestCase{"ZeroSizeY", R"({"translation":[0,0,0],"size":[1,0,1]})", false},
        CameraDataSchemaTestCase{"ZeroSizeZ", R"({"translation":[0,0,0],"size":[1,1,0]})", false},
        CameraDataSchemaTestCase{"NegativeSize", R"({"translation":[0,0,0],"size":[1,-1,1]})",
                                 false},
        CameraDataSchemaTestCase{"ShortSize", R"({"translation":[0,0,0],"size":[1,1]})", false},
        CameraDataSchemaTestCase{"NonNumericSize", R"({"translation":[0,0,0],"size":[1,"bad",1]})",
                                 false}),
    [](const ::testing::TestParamInfo<CameraDataSchemaTestCase>& info) { return info.param.name; });

} // namespace
} // namespace tracker
