// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "coordinate_transformer.hpp"
#include "logger.hpp"
#include "ptz_pose_parser.hpp"
#include "ptz_test_utils.hpp"
#include "scene_parser.hpp"
#include "time_chunk_buffer.hpp"
#include "tracking_worker.hpp"

#include <gtest/gtest.h>

#include <condition_variable>
#include <mutex>

namespace tracker {
namespace {

using ptz::test::kBaseNs;
using ptz::test::ms;

std::vector<Detection> detections() {
    return {Detection{.id = 1, .bounding_box_px = {300, 200, 40, 80}},
            Detection{.id = 2, .bounding_box_px = {100, 300, 60, 120}},
            Detection{.id = 3,
                      .translation = std::array<double, 3>{0.5, -0.2, 2.0},
                      .size = std::array<double, 3>{0.5, 0.5, 1.7},
                      .rotation = std::array<double, 4>{0.0, 0.0, 0.0, 1.0}}};
}

Camera obliqueCamera() {
    Camera camera = ptz::test::camera("cam", true);
    camera.intrinsics.distortion = {0.01, -0.002, 0.0005, 0.0003};
    camera.extrinsics.translation = {1.0, -2.0, 4.0};
    camera.extrinsics.rotation = {-130.0, 10.0, 25.0};
    return camera;
}

void expectSameObjects(const std::vector<rv::tracking::TrackedObject>& a,
                       const std::vector<rv::tracking::TrackedObject>& b, double tolerance) {
    ASSERT_EQ(a.size(), b.size());
    for (size_t i = 0; i < a.size(); ++i) {
        EXPECT_NEAR(a[i].x, b[i].x, tolerance) << i;
        EXPECT_NEAR(a[i].y, b[i].y, tolerance) << i;
        EXPECT_NEAR(a[i].z, b[i].z, tolerance) << i;
        EXPECT_NEAR(a[i].width, b[i].width, tolerance) << i;
        EXPECT_NEAR(a[i].height, b[i].height, tolerance) << i;
        EXPECT_NEAR(a[i].yaw, b[i].yaw, tolerance) << i;
    }
}

// --- Transform passed as an argument ---

TEST(PtzProjectionTest, DefaultTransformEqualsStaticPoseArgument) {
    const auto camera = obliqueCamera();
    const CoordinateTransformer transformer(camera.intrinsics, camera.extrinsics,
                                            ObjectClassConfig::kShiftType2);
    const auto dets = detections();
    expectSameObjects(transformer.transformDetections(dets),
                      transformer.transformDetections(dets, transformer.staticPose()), 0.0);
}

TEST(PtzProjectionTest, HomePoseAsPoseContextMatchesStaticProjection) {
    const auto camera = obliqueCamera();
    const CoordinateTransformer transformer(camera.intrinsics, camera.extrinsics);
    const auto& home = transformer.staticPose().pose_matrix;

    // Round-trip the home pose through a PoseContext payload and the parser
    ptz::test::PoseJson json;
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            json.matrix[static_cast<size_t>(r * 4 + c)] = home(r, c);
        }
    }
    const ptz::PtzMessageParser parser(TRACKER_SCHEMA_DIR);
    const auto parsed = parser.parsePose(json.json());
    ASSERT_TRUE(parsed.pose && parsed.pose->view) << "home pose must be a valid rigid transform";

    const auto dets = detections();
    const auto static_objects = transformer.transformDetections(dets);
    const auto pose_objects = transformer.transformDetections(dets, *parsed.pose->view);
    // 1e-9 m on a ~10 m ray is far below 1e-6 px of reprojection error
    expectSameObjects(static_objects, pose_objects, 1e-9);
}

TEST(PtzProjectionTest, OffHomePoseMovesProjectionAndKeepsIntrinsics) {
    const auto camera = ptz::test::camera("cam", true);
    const CoordinateTransformer transformer(camera.intrinsics, camera.extrinsics);
    const auto intrinsics_before = transformer.getIntrinsicsMatrix();
    const auto distortion_before = transformer.getDistortionCoeffs();
    const auto static_before = transformer.staticPose().pose_matrix;

    const auto turned =
        PoseView::fromRigidMatrix(cv::Matx44d(ptz::test::lookDownMatrix(25.0).data()));
    const auto dets = detections();
    const auto home_objects = transformer.transformDetections(dets);
    const auto turned_objects = transformer.transformDetections(dets, turned);
    ASSERT_EQ(home_objects.size(), turned_objects.size());
    EXPECT_GT(std::hypot(home_objects[1].x - turned_objects[1].x,
                         home_objects[1].y - turned_objects[1].y),
              0.1);
    // A yaw about the optical axis of a nadir camera rotates the footprint about the nadir
    EXPECT_NEAR(std::hypot(home_objects[1].x, home_objects[1].y),
                std::hypot(turned_objects[1].x, turned_objects[1].y), 1e-6);
    EXPECT_EQ(transformer.getIntrinsicsMatrix(), intrinsics_before);
    EXPECT_EQ(transformer.getDistortionCoeffs(), distortion_before);
    EXPECT_EQ(transformer.staticPose().pose_matrix, static_before);
}

TEST(PtzProjectionTest, PoseViewHorizonFallbackForLowCamera) {
    EXPECT_DOUBLE_EQ(PoseView::horizonDistanceFor(0.05), PoseView::kFallbackHorizonDistance);
    EXPECT_GT(PoseView::horizonDistanceFor(-3.0), PoseView::kFallbackHorizonDistance);
}

// --- Buffer: PTZ multi-batch slots ---

DetectionBatch ptzBatch(int64_t offset_ms, size_t detection_count, bool gated = false) {
    DetectionBatch batch;
    batch.camera_id = "ptz";
    batch.timestamp =
        std::chrono::system_clock::time_point(std::chrono::nanoseconds(kBaseNs + ms(offset_ms)));
    batch.timestamp_iso = ptz::test::iso(kBaseNs + ms(offset_ms));
    batch.detections.resize(detection_count);
    batch.ptz_preserve = true;
    batch.ptz_gated = gated;
    return batch;
}

class PtzBufferTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }
    TimeChunkBuffer buffer_;
    TrackingScope scope_{"scene", "person"};
};

TEST_F(PtzBufferTest, KeepsDistinctTimestampsAndReplacesSameTimestamp) {
    buffer_.add(scope_, "ptz", ptzBatch(0, 1));
    buffer_.add(scope_, "ptz", ptzBatch(33, 2));
    buffer_.add(scope_, "ptz", ptzBatch(33, 3));
    auto snapshot = buffer_.pop_all();
    const auto& slot = snapshot[scope_]["ptz"];
    ASSERT_EQ(slot.earlier.size(), 1u);
    EXPECT_EQ(slot.earlier[0].detections.size(), 1u);
    EXPECT_EQ(slot.latest.detections.size(), 3u);
}

TEST_F(PtzBufferTest, GatedHeartbeatNeverDisplacesAndIsReplacedByData) {
    buffer_.add(scope_, "ptz", ptzBatch(0, 2));
    buffer_.add(scope_, "ptz", ptzBatch(33, 0, true));
    auto first = buffer_.pop_all();
    EXPECT_EQ(first[scope_]["ptz"].latest.detections.size(), 2u);
    EXPECT_TRUE(first[scope_]["ptz"].earlier.empty());

    buffer_.add(scope_, "ptz", ptzBatch(0, 0, true));
    buffer_.add(scope_, "ptz", ptzBatch(33, 4));
    auto second = buffer_.pop_all();
    EXPECT_FALSE(second[scope_]["ptz"].latest.ptz_gated);
    EXPECT_EQ(second[scope_]["ptz"].latest.detections.size(), 4u);
    EXPECT_TRUE(second[scope_]["ptz"].earlier.empty());
}

TEST_F(PtzBufferTest, BoundsBatchesPerCameraPerChunk) {
    for (int i = 0; i < 12; ++i) {
        buffer_.add(scope_, "ptz", ptzBatch(10 * i, static_cast<size_t>(i)));
    }
    auto snapshot = buffer_.pop_all();
    const auto& slot = snapshot[scope_]["ptz"];
    EXPECT_EQ(slot.earlier.size() + 1, kMaxPtzBatchesPerCameraPerChunk);
    EXPECT_EQ(slot.latest.detections.size(), 11u);
    EXPECT_EQ(slot.earlier.front().detections.size(), 12u - kMaxPtzBatchesPerCameraPerChunk);
}

TEST_F(PtzBufferTest, StaticCamerasKeepLatestOnly) {
    DetectionBatch first;
    first.detections.resize(1);
    DetectionBatch second;
    second.detections.resize(2);
    second.timestamp = first.timestamp + std::chrono::milliseconds(33);
    buffer_.add(scope_, "static", std::move(first));
    buffer_.add(scope_, "static", std::move(second));
    auto snapshot = buffer_.pop_all();
    EXPECT_TRUE(snapshot[scope_]["static"].earlier.empty());
    EXPECT_EQ(snapshot[scope_]["static"].latest.detections.size(), 2u);
}

// --- Worker: per-batch pose, gated batches ---

class PtzWorkerTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::init("warn");
        config_.max_unreliable_time_s = 0.1;
        cameras_ = {{"ptz", ptz::test::camera("ptz", true)}};
    }
    void TearDown() override { Logger::shutdown(); }

    /// Feed @p chunks chunks 66 ms apart and return the last published tracks.
    std::vector<Track> run(const std::function<DetectionBatch(int)>& make_batch, int chunks) {
        std::mutex mutex;
        std::condition_variable cv;
        std::vector<Track> last;
        int published = 0;
        TrackingWorker worker(
            {"scene", "person"}, "Scene", 4,
            [&](const std::string&, const std::string&, const std::string&, const std::string&,
                const std::vector<Track>& tracks) {
                std::lock_guard lock(mutex);
                last = tracks;
                ++published;
                cv.notify_one();
            },
            config_, cameras_);
        for (int i = 0; i < chunks; ++i) {
            Chunk chunk;
            chunk.scene_id = "scene";
            chunk.category = "person";
            chunk.camera_batches.push_back(make_batch(i));
            worker.try_enqueue(std::move(chunk));
            std::unique_lock lock(mutex);
            cv.wait_for(lock, std::chrono::seconds(2), [&] { return published > i; });
        }
        std::lock_guard lock(mutex);
        return last;
    }

    TrackingConfig config_;
    std::unordered_map<std::string, Camera> cameras_;
};

DetectionBatch timedBatch(int index) {
    DetectionBatch batch;
    batch.camera_id = "ptz";
    batch.timestamp =
        std::chrono::system_clock::time_point(std::chrono::nanoseconds(kBaseNs + ms(66 * index)));
    batch.timestamp_iso = ptz::test::iso(kBaseNs + ms(66 * index));
    batch.detections.push_back(Detection{.id = 1, .bounding_box_px = {300, 200, 40, 80}});
    return batch;
}

TEST_F(PtzWorkerTest, AdmittedBatchProjectsWithItsOwnPose) {
    auto shifted = std::make_shared<ptz::PoseSnapshot>();
    auto matrix = ptz::test::lookDownMatrix(0.0);
    matrix[3] = 5.0; // camera moved 5 m along x
    shifted->valid = true;
    shifted->view = PoseView::fromRigidMatrix(cv::Matx44d(matrix.data()));

    const auto home_tracks = run(timedBatch, 20);
    const auto pose_tracks = run(
        [&shifted](int i) {
            auto batch = timedBatch(i);
            batch.ptz_pose = shifted;
            batch.ptz_preserve = true;
            return batch;
        },
        20);
    ASSERT_EQ(home_tracks.size(), 1u);
    ASSERT_EQ(pose_tracks.size(), 1u);
    EXPECT_NEAR(pose_tracks[0].translation[0] - home_tracks[0].translation[0], 5.0, 0.05);
    EXPECT_NEAR(pose_tracks[0].translation[1], home_tracks[0].translation[1], 0.05);
}

TEST_F(PtzWorkerTest, GatedBatchesNeverInitiateTracks) {
    const auto tracks = run(
        [](int i) {
            auto batch = timedBatch(i);
            batch.detections.clear();
            batch.ptz_gated = true;
            batch.ptz_preserve = true;
            return batch;
        },
        10);
    EXPECT_TRUE(tracks.empty());
}

TEST_F(PtzWorkerTest, GatedBatchesLetExistingTracksAge) {
    int switch_at = 15;
    const auto tracks = run(
        [switch_at](int i) {
            auto batch = timedBatch(i);
            if (i >= switch_at) {
                batch.detections.clear();
                batch.ptz_gated = true;
                batch.ptz_preserve = true;
            }
            return batch;
        },
        switch_at + 40); // 40 * 66 ms > non_measurement_time_dynamic_s
    EXPECT_TRUE(tracks.empty());
}

// --- Scene parsing ---

TEST(PtzSceneParserTest, ParsesPtzCalibrationReference) {
    rapidjson::Document doc;
    doc.Parse(R"({"uid": "s", "name": "S", "cameras": [
        {"uid": "a", "name": "a", "extrinsics": {"translation": [0,0,3], "rotation": [0,0,0],
         "scale": [1,1,1]}, "ptz_calibration": {"calibration_version": "v7", "other": 1}},
        {"uid": "b", "name": "b", "extrinsics": {"translation": [0,0,3], "rotation": [0,0,0],
         "scale": [1,1,1]}, "ptz_calibration": {}},
        {"uid": "c", "name": "c", "extrinsics": {"translation": [0,0,3], "rotation": [0,0,0],
         "scale": [1,1,1]}, "ptz_calibration": null},
        {"uid": "d", "name": "d", "extrinsics": {"translation": [0,0,3], "rotation": [0,0,0],
         "scale": [1,1,1]}}]})");
    const auto scene = detail::parse_scene(doc);
    ASSERT_EQ(scene.cameras.size(), 4u);
    ASSERT_TRUE(scene.cameras[0].ptz.has_value());
    EXPECT_EQ(scene.cameras[0].ptz->calibration_version, std::string("v7"));
    ASSERT_TRUE(scene.cameras[1].ptz.has_value());
    EXPECT_FALSE(scene.cameras[1].ptz->calibration_version.has_value());
    EXPECT_FALSE(scene.cameras[2].ptz.has_value());
    EXPECT_FALSE(scene.cameras[3].ptz.has_value());
}

} // namespace
} // namespace tracker
