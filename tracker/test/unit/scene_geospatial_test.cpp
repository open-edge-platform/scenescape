// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_geospatial.hpp"

#include <gtest/gtest.h>

#include <array>
#include <string>

namespace tracker {
namespace {

std::string pngHeader(uint32_t width, uint32_t height) {
    std::string data(24, '\0');
    const std::array<uint8_t, 8> signature = {0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A};
    for (size_t index = 0; index < signature.size(); ++index) {
        data[index] = static_cast<char>(signature[index]);
    }
    for (size_t index = 0; index < 4; ++index) {
        data[16 + index] = static_cast<char>((width >> (24U - 8U * index)) & 0xFFU);
        data[20 + index] = static_cast<char>((height >> (24U - 8U * index)) & 0xFFU);
    }
    return data;
}

TEST(SceneGeospatialTest, ReadsPngDimensions) {
    EXPECT_EQ(imageDimensions(pngHeader(981, 1112)), (std::pair<size_t, size_t>{981, 1112}));
}

TEST(SceneGeospatialTest, RejectsTruncatedJpegSegment) {
    const std::string jpeg = {static_cast<char>(0xFF), static_cast<char>(0xD8),
                              static_cast<char>(0xFF), static_cast<char>(0xC0),
                              static_cast<char>(0xFF), static_cast<char>(0xFF)};
    EXPECT_FALSE(imageDimensions(jpeg).has_value());
}

TEST(SceneGeospatialTest, RecognizesSupportedImageResources) {
    EXPECT_TRUE(isSupportedImageResource("https://manager/media/map.PNG?version=1"));
    EXPECT_TRUE(isSupportedImageResource("scene.jpeg"));
    EXPECT_FALSE(isSupportedImageResource("scene.glb"));
}

TEST(SceneGeospatialTest, CalculatesMatrixFromImageAndGeospatialCorners) {
    Scene scene;
    scene.output_lla = true;
    scene.map_scale = 5.765182197;
    scene.map_corners_lla =
        std::array<std::array<double, 3>, 4>{std::array<double, 3>{33.842058, -112.136117, 539.0},
                                             std::array<double, 3>{33.842175, -112.134245, 539.0},
                                             std::array<double, 3>{33.843923, -112.134407, 539.0},
                                             std::array<double, 3>{33.843811, -112.136257, 539.0}};

    EXPECT_TRUE(calculateSceneTrsFromImage(scene, pngHeader(981, 1112)));
    EXPECT_TRUE(scene.trs_matrix.has_value());
}

TEST(SceneGeospatialTest, UnsupportedMapDataLeavesMatrixUnset) {
    Scene scene;
    scene.output_lla = true;
    scene.map_scale = 100.0;
    scene.map_corners_lla = std::array<std::array<double, 3>, 4>{};

    EXPECT_FALSE(calculateSceneTrsFromImage(scene, "not an image"));
    EXPECT_FALSE(scene.trs_matrix.has_value());
}

} // namespace
} // namespace tracker