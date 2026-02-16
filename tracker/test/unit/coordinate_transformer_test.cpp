// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @file coordinate_transformer_test.cpp
 * @brief Unit tests for CoordinateTransformer batch API.
 *
 * Reference values were independently computed via the standard transformation
 * pipeline: Euler→rotation matrix, lens undistortion, pose-transform, then
 * ray-plane intersection at z=0. Camera configs match tracker/config/scenes.json.
 *
 * FOOT point = bottom-center of bbox: (x + width/2, y + height)
 */

#include "coordinate_transformer.hpp"
#include "tracking_types.hpp"

#include <gtest/gtest.h>

#include <array>
#include <cmath>
#include <span>
#include <vector>

namespace tracker {
namespace {

// Tolerance for floating point comparisons
constexpr double kRotationTolerance = 1e-8;
constexpr double kWorldTolerance = 1e-5;

//
// Test data structures
//

struct EulerTestCase {
    std::array<double, 3> euler_degrees;
    std::array<std::array<double, 3>, 3> expected_matrix;
};

struct BboxFootTestCase {
    const char* name;
    double bbox_x;
    double bbox_y;
    double bbox_width;
    double bbox_height;
    double world_x;
    double world_y;
};

struct BboxSizeTestCase {
    const char* name;
    double bbox_x;
    double bbox_y;
    double bbox_width;
    double bbox_height;
    double world_width_m;
    double world_height_m;
};

struct CameraTestConfig {
    const char* uid;
    double fx, fy, cx, cy;
    double k1, k2, p1, p2;
    std::array<double, 3> translation;
    std::array<double, 3> rotation;
    std::array<double, 3> scale;
};

//
// Reference data (independently computed via scipy/numpy/cv2)
//

// clang-format off
const std::vector<EulerTestCase> kEulerTestCases = {
  {{0.0, 0.0, 0.0}, {{{1.0, 0.0, 0.0}, {0.0, 1.0, 0.0}, {0.0, 0.0, 1.0}}}},
  {{90.0, 0.0, 0.0}, {{{1.0, 0.0, 0.0}, {0.0, 0.0, -1.0}, {0.0, 1.0, 0.0}}}},
  {{0.0, 90.0, 0.0}, {{{0.0, 0.0, 1.0}, {0.0, 1.0, 0.0}, {-1.0, 0.0, 0.0}}}},
  {{0.0, 0.0, 90.0}, {{{0.0, -1.0, 0.0}, {1.0, 0.0, 0.0}, {0.0, 0.0, 1.0}}}},
  {{45.0, 45.0, 45.0}, {
    {{0.5, -0.5, 0.7071067811865475},
     {0.8535533905932737, 0.1464466094067262, -0.5},
     {0.1464466094067262, 0.8535533905932737, 0.5}}}},
  {{-135.0, 12.0, 19.0}, {
    {{0.9248567261717171, -0.31845370915760085, 0.20791169081775934},
     {-0.36921758785386105, -0.620718944779943, 0.6916548014802256},
     {-0.09120531165622858, -0.7164462483083013, -0.6916548014802253}}}},
  {{-150.6, 42.35, 52.3}, {
    {{0.45194508363994135, -0.5847486084609073, 0.6736577070565727},
     {-0.891557532667238, -0.2711123129225125, 0.3627992278466322},
     {-0.029509444555826048, -0.7645699305392794, -0.64386490352959}}}},
  {{-137.86, -19.44, -15.38}, {
    {{0.9092201984913426, 0.25009954306010873, -0.3328195445229867},
     {0.4119688235919976, -0.6557283360667434, 0.6326942687170207},
     {-0.0600026586376729, -0.7123696848127838, -0.6992346624103716}}}},
};
// clang-format on

const CameraTestConfig kCameraAtaqQcam1 = {
    "atag-qcam1",
    905.0,
    905.0,
    640.0,
    360.0,
    0.0,
    0.0,
    0.0,
    0.0,
    {2.985857104493509, 0.2054078898442529, 2.7150546825598902},
    {-135.08718965001765, 12.682032394455131, 19.24508172546946},
    {1.0, 1.0, 1.0}};

// Bbox foot-to-world reference data for atag-qcam1
const std::vector<BboxFootTestCase> kAtaqQcam1BboxTests = {
    {"center_person", 590.0, 260.0, 100.0, 200.0, 3.6344901016966507, 2.392939581932098},
    {"top_left_person", 10.0, 10.0, 80.0, 160.0, 1.2282759561369583, 6.183174458656931},
    {"bottom_right_person", 1190.0, 550.0, 80.0, 160.0, 4.829388967448987, 0.741790968197878},
};

// Bbox size-to-world reference data for atag-qcam1
const std::vector<BboxSizeTestCase> kAtaqQcam1SizeTests = {
    {"center_person", 590.0, 260.0, 100.0, 200.0, 0.3919666762423937, 0.6622757536806667},
    {"top_left_person", 10.0, 10.0, 80.0, 160.0, 0.5603334504646393, 0.8125457598615778},
    {"bottom_right_person", 1190.0, 550.0, 80.0, 160.0, 0.22245145076251543, 0.3545827145784},
    {"bottom_center_small", 615.0, 620.0, 50.0, 100.0, 0.1543096200319992, 0.2232391508910793},
};

// Yaw to quaternion reference data
struct YawToQuaternionTestCase {
    double yaw_radians;
    std::array<double, 4> expected_quaternion;
};

// clang-format off
const std::vector<YawToQuaternionTestCase> kYawToQuaternionTests = {
    {0.0,                    {0.0, 0.0, 0.0, 1.0}},
    {M_PI / 2,               {0.0, 0.0, 0.7071067811865475, 0.7071067811865476}},
    {M_PI,                   {0.0, 0.0, 1.0, 6.123233995736766e-17}},
    {-M_PI / 2,              {0.0, 0.0, -0.7071067811865475, 0.7071067811865476}},
    {M_PI / 4,               {0.0, 0.0, 0.3826834323650898, 0.9238795325112867}},
    {-M_PI / 4,              {0.0, 0.0, -0.3826834323650898, 0.9238795325112867}},
    {M_PI / 6,               {0.0, 0.0, 0.25881904510252074, 0.9659258262890683}},
    {2.0 * M_PI / 3,         {0.0, 0.0, 0.8660254037844387, 0.49999999999999994}},
    {-M_PI,                  {0.0, 0.0, -1.0, 6.123233995736766e-17}},
    {0.1,                    {0.0, 0.0, 0.049979169270678324, 0.9987502603949663}},
    {-0.1,                   {0.0, 0.0, -0.049979169270678324, 0.9987502603949663}},
};
// clang-format on

// Helper to create CoordinateTransformer from test config
CoordinateTransformer make_transformer(const CameraTestConfig& cfg) {
    CameraIntrinsics intrinsics;
    intrinsics.fx = cfg.fx;
    intrinsics.fy = cfg.fy;
    intrinsics.cx = cfg.cx;
    intrinsics.cy = cfg.cy;
    intrinsics.distortion.k1 = cfg.k1;
    intrinsics.distortion.k2 = cfg.k2;
    intrinsics.distortion.p1 = cfg.p1;
    intrinsics.distortion.p2 = cfg.p2;

    CameraExtrinsics extrinsics;
    extrinsics.translation = cfg.translation;
    extrinsics.rotation = cfg.rotation;
    extrinsics.scale = cfg.scale;

    return CoordinateTransformer(intrinsics, extrinsics);
}

// Helper: create Detection from bbox params
Detection make_detection(float x, float y, float w, float h, int32_t id = 1) {
    return Detection{.id = id, .bounding_box_px = cv::Rect2f(x, y, w, h)};
}

//
// Euler angle to rotation matrix tests
//

TEST(EulerToRotationTest, MatchesReferenceRotations) {
    for (const auto& tc : kEulerTestCases) {
        CameraIntrinsics intrinsics;
        intrinsics.fx = intrinsics.fy = 500.0;
        intrinsics.cx = 320.0;
        intrinsics.cy = 240.0;

        CameraExtrinsics extrinsics;
        extrinsics.rotation = tc.euler_degrees;

        CoordinateTransformer transformer(intrinsics, extrinsics);
        const auto& pose = transformer.getPoseMatrix();

        for (int row = 0; row < 3; ++row) {
            for (int col = 0; col < 3; ++col) {
                EXPECT_NEAR(pose(row, col), tc.expected_matrix[row][col], kRotationTolerance)
                    << "Euler angles [" << tc.euler_degrees[0] << ", " << tc.euler_degrees[1]
                    << ", " << tc.euler_degrees[2] << "] mismatch at (" << row << ", " << col
                    << ")";
            }
        }
    }
}

TEST(EulerToRotationTest, IdentityRotation) {
    CameraIntrinsics intrinsics;
    intrinsics.fx = intrinsics.fy = 500.0;
    intrinsics.cx = 320.0;
    intrinsics.cy = 240.0;

    CameraExtrinsics extrinsics;
    extrinsics.rotation = {0.0, 0.0, 0.0};

    CoordinateTransformer transformer(intrinsics, extrinsics);
    const auto& pose = transformer.getPoseMatrix();

    EXPECT_NEAR(pose(0, 0), 1.0, kRotationTolerance);
    EXPECT_NEAR(pose(0, 1), 0.0, kRotationTolerance);
    EXPECT_NEAR(pose(0, 2), 0.0, kRotationTolerance);
    EXPECT_NEAR(pose(1, 0), 0.0, kRotationTolerance);
    EXPECT_NEAR(pose(1, 1), 1.0, kRotationTolerance);
    EXPECT_NEAR(pose(1, 2), 0.0, kRotationTolerance);
    EXPECT_NEAR(pose(2, 0), 0.0, kRotationTolerance);
    EXPECT_NEAR(pose(2, 1), 0.0, kRotationTolerance);
    EXPECT_NEAR(pose(2, 2), 1.0, kRotationTolerance);
}

//
// Yaw to quaternion tests
//

TEST(YawToQuaternionTest, MatchesReferenceValues) {
    for (const auto& tc : kYawToQuaternionTests) {
        auto result = CoordinateTransformer::yawToQuaternion(tc.yaw_radians);

        EXPECT_NEAR(result[0], tc.expected_quaternion[0], kRotationTolerance)
            << "Yaw " << tc.yaw_radians << " rad: x mismatch";
        EXPECT_NEAR(result[1], tc.expected_quaternion[1], kRotationTolerance)
            << "Yaw " << tc.yaw_radians << " rad: y mismatch";
        EXPECT_NEAR(result[2], tc.expected_quaternion[2], kRotationTolerance)
            << "Yaw " << tc.yaw_radians << " rad: z mismatch";
        EXPECT_NEAR(result[3], tc.expected_quaternion[3], kRotationTolerance)
            << "Yaw " << tc.yaw_radians << " rad: w mismatch";
    }
}

TEST(YawToQuaternionTest, ZeroYawIsIdentity) {
    auto q = CoordinateTransformer::yawToQuaternion(0.0);
    EXPECT_NEAR(q[0], 0.0, kRotationTolerance);
    EXPECT_NEAR(q[1], 0.0, kRotationTolerance);
    EXPECT_NEAR(q[2], 0.0, kRotationTolerance);
    EXPECT_NEAR(q[3], 1.0, kRotationTolerance);
}

TEST(YawToQuaternionTest, PureZAxisRotation) {
    auto q = CoordinateTransformer::yawToQuaternion(1.234);
    EXPECT_EQ(q[0], 0.0) << "x must be exactly 0 for pure Z rotation";
    EXPECT_EQ(q[1], 0.0) << "y must be exactly 0 for pure Z rotation";
}

TEST(YawToQuaternionTest, UnitQuaternion) {
    for (const auto& tc : kYawToQuaternionTests) {
        auto q = CoordinateTransformer::yawToQuaternion(tc.yaw_radians);
        double norm = std::sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
        EXPECT_NEAR(norm, 1.0, 1e-12) << "Yaw " << tc.yaw_radians << " rad: non-unit quaternion";
    }
}

//
// transformDetections — batch API tests
//

TEST(TransformDetectionsTest, EmptyInput) {
    auto transformer = make_transformer(kCameraAtaqQcam1);
    std::vector<Detection> empty;
    auto result = transformer.transformDetections(empty);
    EXPECT_TRUE(result.empty());
}

TEST(TransformDetectionsTest, MatchesPythonReference_Position) {
    // Verify foot-to-world positions match independently computed reference values
    auto transformer = make_transformer(kCameraAtaqQcam1);

    for (const auto& tc : kAtaqQcam1BboxTests) {
        std::vector<Detection> detections = {
            make_detection(static_cast<float>(tc.bbox_x), static_cast<float>(tc.bbox_y),
                           static_cast<float>(tc.bbox_width), static_cast<float>(tc.bbox_height))};

        auto result = transformer.transformDetections(detections);
        ASSERT_EQ(result.size(), 1u) << "Test " << tc.name << ": expected 1 result";
        EXPECT_NEAR(result[0].x, tc.world_x, kWorldTolerance)
            << "Test " << tc.name << " world X mismatch";
        EXPECT_NEAR(result[0].y, tc.world_y, kWorldTolerance)
            << "Test " << tc.name << " world Y mismatch";
        EXPECT_NEAR(result[0].z, 0.0, kWorldTolerance)
            << "Test " << tc.name << " world Z should be 0";
    }
}

TEST(TransformDetectionsTest, MatchesPythonReference_Size) {
    // Verify world-space sizes match independently computed reference values
    auto transformer = make_transformer(kCameraAtaqQcam1);

    for (const auto& tc : kAtaqQcam1SizeTests) {
        std::vector<Detection> detections = {
            make_detection(static_cast<float>(tc.bbox_x), static_cast<float>(tc.bbox_y),
                           static_cast<float>(tc.bbox_width), static_cast<float>(tc.bbox_height))};

        auto result = transformer.transformDetections(detections);
        ASSERT_EQ(result.size(), 1u) << "Test " << tc.name << ": expected 1 result";

        // Size convention: length=width, width=width, height=height
        EXPECT_NEAR(result[0].length, tc.world_width_m, kWorldTolerance)
            << "Test " << tc.name << " world width (length) mismatch";
        EXPECT_NEAR(result[0].width, tc.world_width_m, kWorldTolerance)
            << "Test " << tc.name << " world width mismatch";
        EXPECT_NEAR(result[0].height, tc.world_height_m, kWorldTolerance)
            << "Test " << tc.name << " world height mismatch";
    }
}

TEST(TransformDetectionsTest, PreservesDetectionId) {
    auto transformer = make_transformer(kCameraAtaqQcam1);

    std::vector<Detection> detections = {
        make_detection(590.0f, 260.0f, 100.0f, 200.0f, 42),
        make_detection(10.0f, 10.0f, 80.0f, 160.0f, 7),
    };

    auto result = transformer.transformDetections(detections);
    ASSERT_EQ(result.size(), 2u);
    EXPECT_EQ(result[0].id, 42);
    EXPECT_EQ(result[1].id, 7);
}

TEST(TransformDetectionsTest, MissingIdUsesInvalidObjectId) {
    auto transformer = make_transformer(kCameraAtaqQcam1);

    Detection det;
    det.id = std::nullopt;
    det.bounding_box_px = cv::Rect2f(590.0f, 260.0f, 100.0f, 200.0f);

    std::vector<Detection> detections = {det};
    auto result = transformer.transformDetections(detections);
    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result[0].id, rv::tracking::InvalidObjectId);
}

TEST(TransformDetectionsTest, MultipleBboxesBatch) {
    // Batch with all reference bboxes — verify all are returned with correct positions
    auto transformer = make_transformer(kCameraAtaqQcam1);

    std::vector<Detection> detections;
    for (const auto& tc : kAtaqQcam1BboxTests) {
        detections.push_back(
            make_detection(static_cast<float>(tc.bbox_x), static_cast<float>(tc.bbox_y),
                           static_cast<float>(tc.bbox_width), static_cast<float>(tc.bbox_height)));
    }

    auto result = transformer.transformDetections(detections);
    ASSERT_EQ(result.size(), kAtaqQcam1BboxTests.size());

    for (size_t i = 0; i < kAtaqQcam1BboxTests.size(); ++i) {
        EXPECT_NEAR(result[i].x, kAtaqQcam1BboxTests[i].world_x, kWorldTolerance)
            << "Batch bbox " << i << " X mismatch";
        EXPECT_NEAR(result[i].y, kAtaqQcam1BboxTests[i].world_y, kWorldTolerance)
            << "Batch bbox " << i << " Y mismatch";
    }
}

TEST(TransformDetectionsTest, UsesFootNotCenter) {
    // Verify position corresponds to bottom-center (foot), not bbox center
    CameraIntrinsics intrinsics;
    intrinsics.fx = intrinsics.fy = 500.0;
    intrinsics.cx = 320.0;
    intrinsics.cy = 240.0;

    CameraExtrinsics extrinsics;
    extrinsics.translation = {0.0, 0.0, 3.0};
    extrinsics.rotation = {-90.0, 0.0, 0.0}; // Looking straight down
    extrinsics.scale = {1.0, 1.0, 1.0};

    CoordinateTransformer transformer(intrinsics, extrinsics);

    // Bbox: x=270, y=140, width=100, height=200
    // FOOT = (320, 340), CENTER = (320, 240)
    // For a straight-down camera, these project to different Y world coordinates
    std::vector<Detection> detections = {make_detection(270.0f, 140.0f, 100.0f, 200.0f)};
    auto result = transformer.transformDetections(detections);
    ASSERT_EQ(result.size(), 1u);

    // Also test with a square bbox where foot = center_x, bottom_y
    // Foot pixel (320, 340) vs Center pixel (320, 240) give different world Y
    // For straight-down cam at height 3m, foot_y should differ from center projection
    std::vector<Detection> detections_square = {make_detection(270.0f, 190.0f, 100.0f, 100.0f)};
    auto result_square = transformer.transformDetections(detections_square);
    ASSERT_EQ(result_square.size(), 1u);

    // Both have same bbox center_x (320), but different foot_y (340 vs 290)
    // So world Y should differ
    EXPECT_NE(result[0].y, result_square[0].y)
        << "Different foot positions should produce different world Y";
}

TEST(TransformDetectionsTest, SizeInMetersNotPixels) {
    auto transformer = make_transformer(kCameraAtaqQcam1);

    std::vector<Detection> detections = {make_detection(590.0f, 260.0f, 100.0f, 200.0f)};
    auto result = transformer.transformDetections(detections);
    ASSERT_EQ(result.size(), 1u);

    EXPECT_GT(result[0].length, 0.01) << "Width too small for meters";
    EXPECT_LT(result[0].length, 10.0) << "Width too large, maybe pixel scale?";
    EXPECT_GT(result[0].height, 0.01) << "Height too small for meters";
    EXPECT_LT(result[0].height, 10.0) << "Height too large, maybe pixel scale?";
}

TEST(TransformDetectionsTest, LargerBboxProducesLargerSize) {
    auto transformer = make_transformer(kCameraAtaqQcam1);

    std::vector<Detection> detections = {
        make_detection(590.0f, 260.0f, 50.0f, 100.0f),  // small
        make_detection(590.0f, 260.0f, 100.0f, 200.0f), // large
    };

    auto result = transformer.transformDetections(detections);
    ASSERT_EQ(result.size(), 2u);

    EXPECT_GT(result[1].length, result[0].length)
        << "Larger bbox should produce larger world width";
    EXPECT_GT(result[1].height, result[0].height)
        << "Larger bbox should produce larger world height";
}

TEST(TransformDetectionsTest, LargeBatch_1000Detections) {
    // Smoke test: 1000 detections should process without crashes or data races
    auto transformer = make_transformer(kCameraAtaqQcam1);

    std::vector<Detection> detections;
    detections.reserve(1000);
    for (int i = 0; i < 1000; ++i) {
        float x = static_cast<float>(50 + (i % 1100)); // spread across image
        float y = static_cast<float>(50 + (i / 10));
        detections.push_back(make_detection(x, y, 80.0f, 160.0f, i));
    }

    auto result = transformer.transformDetections(detections);
    EXPECT_EQ(result.size(), 1000u);

    // Verify IDs are preserved in order
    for (size_t i = 0; i < result.size(); ++i) {
        EXPECT_EQ(result[i].id, static_cast<int32_t>(i));
    }

    // Verify all positions are finite
    for (const auto& obj : result) {
        EXPECT_TRUE(std::isfinite(obj.x)) << "Non-finite x for id " << obj.id;
        EXPECT_TRUE(std::isfinite(obj.y)) << "Non-finite y for id " << obj.id;
        EXPECT_TRUE(std::isfinite(obj.length)) << "Non-finite length for id " << obj.id;
        EXPECT_TRUE(std::isfinite(obj.height)) << "Non-finite height for id " << obj.id;
    }
}

//
// Camera origin test
//

TEST(CoordinateTransformerTest, CameraOriginFromTranslation) {
    CameraIntrinsics intrinsics;
    intrinsics.fx = intrinsics.fy = 500.0;
    intrinsics.cx = 320.0;
    intrinsics.cy = 240.0;

    CameraExtrinsics extrinsics;
    extrinsics.translation = {1.5, 2.5, 3.5};
    extrinsics.rotation = {0.0, 0.0, 0.0};
    extrinsics.scale = {1.0, 1.0, 1.0};

    CoordinateTransformer transformer(intrinsics, extrinsics);
    auto origin = transformer.getCameraOrigin();

    EXPECT_NEAR(origin.x, 1.5, 1e-10);
    EXPECT_NEAR(origin.y, 2.5, 1e-10);
    EXPECT_NEAR(origin.z, 3.5, 1e-10);
}

//
// Horizon culling: upward-pointing rays still produce valid results
//

TEST(CoordinateTransformerTest, UpwardRayReturnsValidResult) {
    CameraIntrinsics intrinsics;
    intrinsics.fx = intrinsics.fy = 500.0;
    intrinsics.cx = 320.0;
    intrinsics.cy = 240.0;

    CameraExtrinsics extrinsics;
    extrinsics.translation = {0.0, 0.0, 3.0};
    extrinsics.rotation = {-45.0, 0.0, 0.0}; // Looking 45° down
    extrinsics.scale = {1.0, 1.0, 1.0};

    CoordinateTransformer transformer(intrinsics, extrinsics);

    // Bbox near top of image where ray may point upward
    std::vector<Detection> detections = {make_detection(280.0f, 0.0f, 80.0f, 40.0f)};
    auto result = transformer.transformDetections(detections);

    // Should return a valid result (horizon culling, not failure)
    EXPECT_EQ(result.size(), 1u);
}

} // namespace
} // namespace tracker
