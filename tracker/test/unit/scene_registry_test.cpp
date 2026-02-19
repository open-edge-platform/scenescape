// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_registry.hpp"

#include <gtest/gtest.h>

#include <algorithm>

namespace tracker {
namespace {

// Helper to create a simple camera
Camera make_camera(const std::string& uid, const std::string& name = "") {
    Camera cam;
    cam.uid = uid;
    cam.name = name.empty() ? uid : name;
    cam.intrinsics.fx = 500.0;
    cam.intrinsics.fy = 500.0;
    cam.intrinsics.cx = 320.0;
    cam.intrinsics.cy = 240.0;
    // distortion defaults to 0.0 via struct initialization
    return cam;
}

// Helper to create a simple scene
Scene make_scene(const std::string& uid, const std::string& name, std::vector<Camera> cameras) {
    Scene scene;
    scene.uid = uid;
    scene.name = name;
    scene.cameras = std::move(cameras);
    return scene;
}

//
// Basic registration tests
//

TEST(SceneRegistryTest, EmptyRegistryReturnsNullptr) {
    SceneRegistry registry;

    EXPECT_TRUE(registry.empty());
    EXPECT_EQ(registry.scene_count(), 0);
    EXPECT_EQ(registry.camera_count(), 0);
    EXPECT_EQ(registry.find_scene_for_camera("any-camera"), nullptr);
    EXPECT_EQ(registry.find_camera("any-camera"), nullptr);
}

TEST(SceneRegistryTest, RegisterSingleSceneWithSingleCamera) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {make_scene("scene-001", "Test Scene", {make_camera("cam-001")})};

    registry.register_scenes(scenes);

    EXPECT_FALSE(registry.empty());
    EXPECT_EQ(registry.scene_count(), 1);
    EXPECT_EQ(registry.camera_count(), 1);

    const Scene* found = registry.find_scene_for_camera("cam-001");
    ASSERT_NE(found, nullptr);
    EXPECT_EQ(found->uid, "scene-001");
    EXPECT_EQ(found->name, "Test Scene");
}

TEST(SceneRegistryTest, RegisterMultipleScenesWithMultipleCameras) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {
        make_scene("scene-001", "Queuing", {make_camera("qcam1"), make_camera("qcam2")}),
        make_scene("scene-002", "Retail",
                   {make_camera("rcam1"), make_camera("rcam2"), make_camera("rcam3")})};

    registry.register_scenes(scenes);

    EXPECT_EQ(registry.scene_count(), 2);
    EXPECT_EQ(registry.camera_count(), 5);

    // Check Queuing scene cameras
    const Scene* queuing = registry.find_scene_for_camera("qcam1");
    ASSERT_NE(queuing, nullptr);
    EXPECT_EQ(queuing->name, "Queuing");

    EXPECT_EQ(registry.find_scene_for_camera("qcam2"), queuing);

    // Check Retail scene cameras
    const Scene* retail = registry.find_scene_for_camera("rcam1");
    ASSERT_NE(retail, nullptr);
    EXPECT_EQ(retail->name, "Retail");

    EXPECT_EQ(registry.find_scene_for_camera("rcam2"), retail);
    EXPECT_EQ(registry.find_scene_for_camera("rcam3"), retail);
}

//
// Camera lookup tests
//

TEST(SceneRegistryTest, FindCameraReturnsCorrectCalibration) {
    SceneRegistry registry;

    Camera cam;
    cam.uid = "calibrated-cam";
    cam.name = "Calibrated Camera";
    cam.intrinsics.fx = 905.0;
    cam.intrinsics.fy = 905.0;
    cam.intrinsics.cx = 640.0;
    cam.intrinsics.cy = 360.0;
    cam.intrinsics.distortion.k1 = 0.1;
    cam.intrinsics.distortion.k2 = 0.2;
    cam.intrinsics.distortion.p1 = 0.01;
    cam.intrinsics.distortion.p2 = 0.02;

    std::vector<Scene> scenes = {make_scene("scene-001", "Test", {cam})};
    registry.register_scenes(scenes);

    const Camera* found = registry.find_camera("calibrated-cam");
    ASSERT_NE(found, nullptr);
    EXPECT_EQ(found->name, "Calibrated Camera");
    EXPECT_DOUBLE_EQ(found->intrinsics.fx, 905.0);
    EXPECT_DOUBLE_EQ(found->intrinsics.fy, 905.0);
    EXPECT_DOUBLE_EQ(found->intrinsics.cx, 640.0);
    EXPECT_DOUBLE_EQ(found->intrinsics.cy, 360.0);
    EXPECT_DOUBLE_EQ(found->intrinsics.distortion.k1, 0.1);
    EXPECT_DOUBLE_EQ(found->intrinsics.distortion.k2, 0.2);
}

TEST(SceneRegistryTest, UnknownCameraReturnsNullptr) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {make_scene("scene-001", "Test", {make_camera("known-cam")})};
    registry.register_scenes(scenes);

    EXPECT_EQ(registry.find_scene_for_camera("unknown-cam"), nullptr);
    EXPECT_EQ(registry.find_camera("unknown-cam"), nullptr);
}

//
// Get camera IDs for scene tests
//

TEST(SceneRegistryTest, GetCameraIdsForScene) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {
        make_scene("scene-001", "Queuing", {make_camera("qcam1"), make_camera("qcam2")}),
        make_scene("scene-002", "Retail", {make_camera("rcam1")})};
    registry.register_scenes(scenes);

    auto queuing_cams = registry.get_camera_ids_for_scene("scene-001");
    EXPECT_EQ(queuing_cams.size(), 2);
    EXPECT_EQ(queuing_cams[0], "qcam1");
    EXPECT_EQ(queuing_cams[1], "qcam2");

    auto retail_cams = registry.get_camera_ids_for_scene("scene-002");
    EXPECT_EQ(retail_cams.size(), 1);
    EXPECT_EQ(retail_cams[0], "rcam1");

    // Unknown scene returns empty
    auto unknown = registry.get_camera_ids_for_scene("unknown-scene");
    EXPECT_TRUE(unknown.empty());
}

//
// Get all scenes test
//

TEST(SceneRegistryTest, GetAllScenes) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {make_scene("scene-001", "Queuing", {make_camera("qcam1")}),
                                 make_scene("scene-002", "Retail", {make_camera("rcam1")})};
    registry.register_scenes(scenes);

    const auto& all_scenes = registry.get_all_scenes();
    EXPECT_EQ(all_scenes.size(), 2);
    EXPECT_EQ(all_scenes[0].uid, "scene-001");
    EXPECT_EQ(all_scenes[1].uid, "scene-002");
}

TEST(SceneRegistryTest, GetAllCameraIds) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {
        make_scene("scene-001", "Queuing", {make_camera("qcam1"), make_camera("qcam2")}),
        make_scene("scene-002", "Retail", {make_camera("rcam1")})};
    registry.register_scenes(scenes);

    auto camera_ids = registry.get_all_camera_ids();
    EXPECT_EQ(camera_ids.size(), 3);

    // Check all cameras are present (order may vary due to unordered_map)
    std::sort(camera_ids.begin(), camera_ids.end());
    EXPECT_EQ(camera_ids[0], "qcam1");
    EXPECT_EQ(camera_ids[1], "qcam2");
    EXPECT_EQ(camera_ids[2], "rcam1");
}

TEST(SceneRegistryTest, GetAllCameraIdsEmptyRegistry) {
    SceneRegistry registry;

    auto camera_ids = registry.get_all_camera_ids();
    EXPECT_TRUE(camera_ids.empty());
}

//
// Duplicate camera detection tests
//

TEST(SceneRegistryTest, DuplicateCameraThrowsException) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {
        make_scene("scene-001", "First Scene", {make_camera("shared-cam")}),
        make_scene("scene-002", "Second Scene", {make_camera("shared-cam")})};

    EXPECT_THROW(
        {
            try {
                registry.register_scenes(scenes);
            } catch (const DuplicateCameraError& e) {
                EXPECT_EQ(e.camera_id(), "shared-cam");
                EXPECT_EQ(e.scene1(), "First Scene");
                EXPECT_EQ(e.scene2(), "Second Scene");
                EXPECT_NE(std::string(e.what()).find("shared-cam"), std::string::npos);
                throw;
            }
        },
        DuplicateCameraError);
}

TEST(SceneRegistryTest, DuplicateCameraWithinSameSceneThrows) {
    SceneRegistry registry;

    std::vector<Scene> scenes = {
        make_scene("scene-001", "Test", {make_camera("cam-001"), make_camera("cam-001")})};

    EXPECT_THROW(registry.register_scenes(scenes), DuplicateCameraError);
}

//
// Re-registration tests
//

TEST(SceneRegistryTest, ReRegisterClearsOldData) {
    SceneRegistry registry;

    // First registration
    registry.register_scenes({make_scene("old-scene", "Old", {make_camera("old-cam")})});

    EXPECT_NE(registry.find_scene_for_camera("old-cam"), nullptr);

    // Re-register with new scenes
    registry.register_scenes({make_scene("new-scene", "New", {make_camera("new-cam")})});

    EXPECT_EQ(registry.find_scene_for_camera("old-cam"), nullptr);
    EXPECT_NE(registry.find_scene_for_camera("new-cam"), nullptr);
    EXPECT_EQ(registry.scene_count(), 1);
    EXPECT_EQ(registry.camera_count(), 1);
}

//
// Edge case tests
//

TEST(SceneRegistryTest, EmptySceneListClearsRegistry) {
    SceneRegistry registry;

    registry.register_scenes({make_scene("scene-001", "Test", {make_camera("cam-001")})});
    EXPECT_FALSE(registry.empty());

    registry.register_scenes({});
    EXPECT_TRUE(registry.empty());
}

} // namespace
} // namespace tracker
