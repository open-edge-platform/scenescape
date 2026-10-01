// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "external_source.hpp"

#include <gtest/gtest.h>

#include <chrono>

namespace tracker {
namespace {

using namespace std::chrono_literals;

const auto kNow = std::chrono::system_clock::time_point{1000s};

Scene makeScene(const std::string& id = "scene-1") {
    Scene scene;
    scene.uid = id;
    scene.name = id;
    return scene;
}

ExternalPose makeScenePose(const std::array<double, 3>& translation = {1.0, 2.0, 3.0}) {
    return ExternalPose{.reference_frame = "scene", .position = translation};
}

TEST(ExternalSourcePoseCacheTest, ResolvesTrustedScenePoseAndTransformsPoint) {
    ExternalSourcePoseCache cache;
    const auto result = cache.resolve(makeScene(), "agent-1", makeScenePose(), kNow, true);

    ASSERT_TRUE(result.source_to_scene.has_value());
    EXPECT_TRUE(result.reason.empty());
    const auto point = transformExternalPoint(*result.source_to_scene, {4.0, 5.0, 6.0});
    EXPECT_DOUBLE_EQ(point[0], 5.0);
    EXPECT_DOUBLE_EQ(point[1], 7.0);
    EXPECT_DOUBLE_EQ(point[2], 9.0);
}

TEST(ExternalSourcePoseCacheTest, RejectsUntrustedScenePose) {
    ExternalSourcePoseCache cache;
    const auto result = cache.resolve(makeScene(), "agent-1", makeScenePose(), kNow, false);

    EXPECT_FALSE(result.source_to_scene.has_value());
    EXPECT_EQ(result.reason, kReasonUntrustedScenePose);
}

TEST(ExternalSourcePoseCacheTest, ResolvesWgs84OriginThroughSceneTrsMatrix) {
    const std::array<double, 3> lla{37.7749, -122.4194, 15.0};
    const auto ecef = convertLlaToEcef(lla);
    auto scene = makeScene();
    scene.trs_matrix = std::array<std::array<double, 4>, 4>{
        std::array<double, 4>{1.0, 0.0, 0.0, ecef[0]},
        std::array<double, 4>{0.0, 1.0, 0.0, ecef[1]},
        std::array<double, 4>{0.0, 0.0, 1.0, ecef[2]}, std::array<double, 4>{0.0, 0.0, 0.0, 1.0}};
    ExternalPose pose{.reference_frame = "wgs84", .position = lla};
    ExternalSourcePoseCache cache;

    const auto result = cache.resolve(scene, "agent-1", pose, kNow, false);

    ASSERT_TRUE(result.source_to_scene.has_value()) << result.reason;
    const auto origin = transformExternalPoint(*result.source_to_scene, {0.0, 0.0, 0.0});
    EXPECT_NEAR(origin[0], 0.0, 1e-9);
    EXPECT_NEAR(origin[1], 0.0, 1e-9);
    EXPECT_NEAR(origin[2], 0.0, 1e-9);
}

TEST(GeospatialTransformTest, CalculatesPythonEquivalentMatrixFromMapCorners) {
    constexpr double pixels_per_meter = 5.765182197;
    const double width = 981.0 / pixels_per_meter;
    const double height = 1112.0 / pixels_per_meter;
    const std::array<std::array<double, 3>, 4> map_corners = {
        std::array<double, 3>{0.0, 0.0, 0.0}, std::array<double, 3>{width, 0.0, 0.0},
        std::array<double, 3>{width, height, 0.0}, std::array<double, 3>{0.0, height, 0.0}};
    const std::array<std::array<double, 3>, 4> lla_corners = {
        std::array<double, 3>{33.842058, -112.136117, 539.0},
        std::array<double, 3>{33.842175, -112.134245, 539.0},
        std::array<double, 3>{33.843923, -112.134407, 539.0},
        std::array<double, 3>{33.843811, -112.136257, 539.0}};
    auto scene = makeScene();
    scene.trs_matrix = calculateTrsLocalToEcef(map_corners, lla_corners);
    ExternalSourcePoseCache cache;

    for (size_t index = 0; index < map_corners.size(); ++index) {
        ExternalPose pose{.reference_frame = "wgs84", .position = lla_corners[index]};
        const auto result =
            cache.resolve(scene, "agent-" + std::to_string(index), pose, kNow, false);
        ASSERT_TRUE(result.source_to_scene.has_value()) << result.reason;
        const auto local = transformExternalPoint(*result.source_to_scene, {0.0, 0.0, 0.0});
        EXPECT_NEAR(local[0], map_corners[index][0], 1.0);
        EXPECT_NEAR(local[1], map_corners[index][1], 1.0);
        EXPECT_NEAR(local[2], map_corners[index][2], 1.0);
    }
}

TEST(ExternalSourcePoseCacheTest, RejectsWgs84WithoutTrsMatrix) {
    ExternalSourcePoseCache cache;
    ExternalPose pose{.reference_frame = "wgs84", .position = {0.0, 0.0, 0.0}};

    const auto result = cache.resolve(makeScene(), "agent-1", pose, kNow, false);

    EXPECT_FALSE(result.source_to_scene.has_value());
    EXPECT_EQ(result.reason, kReasonSceneGeoreferenceUnavailable);
}

TEST(ExternalSourcePoseCacheTest, RejectsWgs84WithSingularTrsMatrix) {
    auto scene = makeScene();
    scene.trs_matrix = TrsMatrix{};
    ExternalSourcePoseCache cache;
    ExternalPose pose{.reference_frame = "wgs84", .position = {0.0, 0.0, 0.0}};

    const auto result = cache.resolve(scene, "agent-1", pose, kNow, false);

    EXPECT_FALSE(result.source_to_scene.has_value());
    EXPECT_EQ(result.reason, kReasonSceneGeoreferenceUnavailable);
}

TEST(ExternalSourcePoseCacheTest, ReusesLivePoseAndExpiresIt) {
    ExternalSourcePoseCache cache(30.0);
    ASSERT_TRUE(cache.resolve(makeScene(), "agent-1", makeScenePose(), kNow, true)
                    .source_to_scene.has_value());

    EXPECT_TRUE(cache.resolve(makeScene(), "agent-1", std::nullopt, kNow + 30s, false)
                    .source_to_scene.has_value());
    const auto expired = cache.resolve(makeScene(), "agent-1", std::nullopt, kNow + 31s, false);
    EXPECT_FALSE(expired.source_to_scene.has_value());
    EXPECT_EQ(expired.reason, kReasonPoseExpired);
}

TEST(ExternalSourcePoseCacheTest, OutOfOrderPoseDoesNotReplaceNewerPose) {
    ExternalSourcePoseCache cache;
    ASSERT_TRUE(
        cache.resolve(makeScene(), "agent-1", makeScenePose({10.0, 0.0, 0.0}), kNow + 10s, true)
            .source_to_scene.has_value());

    const auto result =
        cache.resolve(makeScene(), "agent-1", makeScenePose({1.0, 0.0, 0.0}), kNow, true);

    ASSERT_TRUE(result.source_to_scene.has_value());
    const auto origin = transformExternalPoint(*result.source_to_scene, {0.0, 0.0, 0.0});
    EXPECT_DOUBLE_EQ(origin[0], 10.0);
}

TEST(ExternalSourcePoseCacheTest, SweepsOnlyConfiguredChunk) {
    ExternalSourcePoseCache cache(1.0, 1);
    ASSERT_TRUE(cache.resolve(makeScene("scene-1"), "agent-1", makeScenePose(), kNow, true)
                    .source_to_scene.has_value());
    ASSERT_TRUE(cache.resolve(makeScene("scene-2"), "agent-1", makeScenePose(), kNow, true)
                    .source_to_scene.has_value());

    EXPECT_EQ(cache.sweepExpired(kNow + 2s), 1);
    EXPECT_EQ(cache.scenesWithLiveCache("agent-1", kNow + 2s).size(), 0);
    EXPECT_EQ(cache.sweepExpired(kNow + 2s), 1);
}

TEST(ExternalSourcePoseCacheTest, SweepAdvancesPastLiveEntries) {
    ExternalSourcePoseCache cache(1.0, 1, 0.0);
    ASSERT_TRUE(cache.resolve(makeScene("scene-live"), "agent-1", makeScenePose(), kNow, true)
                    .source_to_scene.has_value());
    ASSERT_TRUE(
        cache.resolve(makeScene("scene-expired"), "agent-1", makeScenePose(), kNow - 5s, true)
            .source_to_scene.has_value());

    EXPECT_EQ(cache.sweepExpired(kNow), 0);
    EXPECT_EQ(cache.sweepExpired(kNow), 1);
}

TEST(IdentityClaimRegistryTest, RejectsDifferentSourceUntilClaimExpires) {
    IdentityClaimRegistry registry(30.0);

    EXPECT_TRUE(registry.claim("scene-1", "person", "agent-1", "tag-1", kNow).first);
    const auto collision = registry.claim("scene-1", "person", "agent-2", "tag-1", kNow + 1s);
    EXPECT_FALSE(collision.first);
    EXPECT_EQ(collision.second, kReasonIdentityCollision);
    EXPECT_TRUE(registry.claim("scene-1", "person", "agent-2", "tag-1", kNow + 31s).first);
}

TEST(IdentityClaimRegistryTest, ClaimsAreIsolatedBySceneAndCategory) {
    IdentityClaimRegistry registry;
    EXPECT_TRUE(registry.claim("scene-1", "person", "agent-1", "tag-1", kNow).first);

    EXPECT_TRUE(registry.claim("scene-2", "person", "agent-2", "tag-1", kNow).first);
    EXPECT_TRUE(registry.claim("scene-1", "vehicle", "agent-2", "tag-1", kNow).first);
}

TEST(IdentityClaimRegistryTest, SameSourceOutOfOrderClaimDoesNotShortenLease) {
    IdentityClaimRegistry registry(30.0);
    EXPECT_TRUE(registry.claim("scene-1", "person", "agent-1", "tag-1", kNow + 10s).first);
    EXPECT_TRUE(registry.claim("scene-1", "person", "agent-1", "tag-1", kNow).first);

    EXPECT_FALSE(registry.claim("scene-1", "person", "agent-2", "tag-1", kNow + 31s).first);
}

TEST(IdentityClaimRegistryTest, SweepAdvancesPastLiveClaims) {
    IdentityClaimRegistry registry(1.0, 1, 0.0);
    EXPECT_TRUE(registry.claim("scene-1", "person", "agent-1", "live", kNow).first);
    EXPECT_TRUE(registry.claim("scene-1", "person", "agent-1", "expired", kNow - 5s).first);

    EXPECT_EQ(registry.sweepExpired(kNow), 0);
    EXPECT_EQ(registry.sweepExpired(kNow), 1);
}

} // namespace
} // namespace tracker