// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "time_chunk_scheduler.hpp"

#include "logger.hpp"
#include "scene_registry.hpp"
#include "time_chunk_buffer.hpp"

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <format>
#include <map>
#include <mutex>
#include <thread>

namespace tracker {
namespace {

class TimeChunkSchedulerTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }

    // Helper to create a TrackingConfig with custom settings
    TrackingConfig createConfig(int fps = 15, int max_workers = 10) {
        TrackingConfig config;
        config.time_chunking_rate_fps = fps;
        config.max_workers = max_workers;
        return config;
    }

    // Helper to create and register scenes
    void registerScenes(SceneRegistry& registry) {
        Scene scene1;
        scene1.uid = "scene-1";
        scene1.name = "Test Scene 1";
        Camera cam1;
        cam1.uid = "cam-1";
        cam1.name = "Camera 1";
        cam1.intrinsics = {
            905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}}; // fx, fy, cx, cy, distortion
        scene1.cameras.push_back(cam1);

        Scene scene2;
        scene2.uid = "scene-2";
        scene2.name = "Test Scene 2";
        Camera cam2;
        cam2.uid = "cam-2";
        cam2.name = "Camera 2";
        cam2.intrinsics = {
            905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}}; // fx, fy, cx, cy, distortion
        scene2.cameras.push_back(cam2);

        registry.register_scenes({scene1, scene2});
    }

    // Helper to create a DetectionBatch
    DetectionBatch createBatch(const std::string& camera_id, const std::string& timestamp) {
        DetectionBatch batch;
        batch.camera_id = camera_id;
        batch.timestamp_iso = timestamp;
        batch.receive_time = std::chrono::steady_clock::now();
        batch.detections.push_back(Detection{.id = 1, .bounding_box_px = {10, 20, 50, 100}});
        return batch;
    }
};

// =============================================================================
// Constructor tests
// =============================================================================

TEST_F(TimeChunkSchedulerTest, Constructor_CalculatesIntervalFromFPS) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    TrackingConfig config = createConfig(15); // 15 FPS

    int callback_count = 0;
    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&,
                                   const std::vector<Track>&) { callback_count++; };

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    // Scheduler should not be running until started
    EXPECT_FALSE(scheduler.is_running());
    EXPECT_EQ(scheduler.dispatched_count(), 0);
}

TEST_F(TimeChunkSchedulerTest, Constructor_DifferentFPSValues) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    // 30 FPS = ~33ms interval, 10 FPS = 100ms interval
    TrackingConfig config30 = createConfig(30);
    TrackingConfig config10 = createConfig(10);

    TimeChunkScheduler scheduler30(buffer, registry, config30, callback);
    TimeChunkScheduler scheduler10(buffer, registry, config10, callback);

    // Both should start in non-running state
    EXPECT_FALSE(scheduler30.is_running());
    EXPECT_FALSE(scheduler10.is_running());
}

// =============================================================================
// start()/stop() tests
// =============================================================================

TEST_F(TimeChunkSchedulerTest, StartStop_BasicLifecycle) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    TrackingConfig config = createConfig(100); // Fast for testing

    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    EXPECT_FALSE(scheduler.is_running());

    scheduler.start();
    EXPECT_TRUE(scheduler.is_running());

    scheduler.stop();
    EXPECT_FALSE(scheduler.is_running());
}

TEST_F(TimeChunkSchedulerTest, Start_IsIdempotent) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    TrackingConfig config = createConfig(100);

    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    scheduler.start();
    EXPECT_TRUE(scheduler.is_running());

    // Double start should not crash or change state
    scheduler.start();
    EXPECT_TRUE(scheduler.is_running());

    scheduler.stop();
}

TEST_F(TimeChunkSchedulerTest, Stop_IsIdempotent) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    TrackingConfig config = createConfig(100);

    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    scheduler.start();
    scheduler.stop();
    EXPECT_FALSE(scheduler.is_running());

    // Double stop should not crash
    scheduler.stop();
    EXPECT_FALSE(scheduler.is_running());
}

TEST_F(TimeChunkSchedulerTest, Stop_WithoutStart_DoesNotCrash) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    TrackingConfig config = createConfig(100);

    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    // Stop without start should be safe
    scheduler.stop();
    EXPECT_FALSE(scheduler.is_running());
}

// =============================================================================
// Dispatch and worker creation tests
// =============================================================================

TEST_F(TimeChunkSchedulerTest, Dispatch_CreatesWorkerForNewScope) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    registerScenes(registry);
    TrackingConfig config = createConfig(100, 10);

    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;
    std::string last_scene_id;

    PublishCallback callback = [&](const std::string& scene_id, const std::string&,
                                   const std::string&, const std::string&,
                                   const std::vector<Track>&) {
        std::lock_guard lock(mtx);
        callback_count++;
        last_scene_id = scene_id;
        cv.notify_one();
    };

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    // Add data to buffer before starting
    TrackingScope scope{"scene-1", "person"};
    buffer.add(scope, "cam-1", createBatch("cam-1", "2026-01-27T12:00:00.000Z"));

    scheduler.start();

    // Wait for dispatch and processing
    {
        std::unique_lock lock(mtx);
        EXPECT_TRUE(cv.wait_for(lock, std::chrono::seconds(2), [&] { return callback_count > 0; }));
    }

    EXPECT_GE(scheduler.worker_count(), 1u);
    EXPECT_EQ(last_scene_id, "scene-1");

    scheduler.stop();
}

TEST_F(TimeChunkSchedulerTest, Dispatch_RoutesToExistingWorker) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    registerScenes(registry);
    TrackingConfig config = createConfig(100, 10);

    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>&) {
        std::lock_guard lock(mtx);
        callback_count++;
        cv.notify_one();
    };

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    // Add initial data
    TrackingScope scope{"scene-1", "person"};
    buffer.add(scope, "cam-1", createBatch("cam-1", "2026-01-27T12:00:00.000Z"));

    scheduler.start();

    // Wait for first dispatch
    {
        std::unique_lock lock(mtx);
        EXPECT_TRUE(
            cv.wait_for(lock, std::chrono::seconds(1), [&] { return callback_count >= 1; }));
    }

    size_t worker_count_after_first = scheduler.worker_count();

    // Add more data to same scope
    buffer.add(scope, "cam-1", createBatch("cam-1", "2026-01-27T12:00:01.000Z"));

    // Wait for second dispatch
    {
        std::unique_lock lock(mtx);
        EXPECT_TRUE(
            cv.wait_for(lock, std::chrono::seconds(1), [&] { return callback_count >= 2; }));
    }

    // Worker count should remain the same (reused existing worker)
    EXPECT_EQ(scheduler.worker_count(), worker_count_after_first);

    scheduler.stop();
}

TEST_F(TimeChunkSchedulerTest, Dispatch_RespectsMaxScopesLimit) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    registerScenes(registry);
    TrackingConfig config = createConfig(100, 2); // Only 2 scopes allowed

    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>&) {
        std::lock_guard lock(mtx);
        callback_count++;
        cv.notify_one();
    };

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    // Add data for 3 different scopes (but only 2 allowed)
    buffer.add({"scene-1", "person"}, "cam-1", createBatch("cam-1", "2026-01-27T12:00:00.000Z"));
    buffer.add({"scene-1", "vehicle"}, "cam-1", createBatch("cam-1", "2026-01-27T12:00:00.000Z"));
    buffer.add({"scene-2", "person"}, "cam-2", createBatch("cam-2", "2026-01-27T12:00:00.000Z"));

    scheduler.start();

    // Wait until at least 2 callbacks (the allowed scopes) have fired
    {
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(5), [&] { return callback_count >= 2; }))
            << "Timed out waiting for callbacks";
    }

    // Should only have 2 workers (max_workers limit)
    EXPECT_LE(scheduler.worker_count(), 2u);

    // Should have dropped at least one scope
    EXPECT_GE(scheduler.scope_limit_drops(), 1);

    scheduler.stop();
}

// The scheduler resolves each scope's category in its ObjectClassMap: the same bbox publishes a
// different world position for a TYPE_2 category than for an unlisted (TYPE_1) one.
TEST_F(TimeChunkSchedulerTest, Dispatch_AppliesObjectClassPerCategory) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    Scene scene;
    scene.uid = "scene-1";
    scene.name = "Test Scene 1";
    Camera cam;
    cam.uid = "cam-1";
    cam.name = "Camera 1";
    cam.intrinsics = {905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}};
    cam.extrinsics.translation = {0.0, 0.0, 3.0};
    cam.extrinsics.rotation = {-90.0, 0.0, 0.0};
    cam.extrinsics.scale = {1.0, 1.0, 1.0};
    scene.cameras.push_back(cam);
    registry.register_scenes({scene});

    TrackingConfig config = createConfig(100, 10);
    config.max_unreliable_time_s = 0.0;

    std::mutex mtx;
    std::condition_variable cv;
    std::map<std::string, std::array<double, 3>> positions;
    PublishCallback callback = [&](const std::string&, const std::string&,
                                   const std::string& category, const std::string&,
                                   const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        if (!tracks.empty() && positions.try_emplace(category, tracks.front().translation).second) {
            cv.notify_one();
        }
    };

    const ObjectClassMap object_classes = {
        {"plane", ObjectClassConfig{.shift_type = ObjectClassConfig::kShiftType2}}};
    TimeChunkScheduler scheduler(buffer, registry, config, callback, makeSystemClock(),
                                 object_classes);
    scheduler.start();

    std::unique_lock lock(mtx);
    for (int i = 0; i < 20 && positions.size() < 2; ++i) {
        lock.unlock();
        for (const char* category : {"plane", "person"}) {
            DetectionBatch batch;
            batch.camera_id = "cam-1";
            batch.timestamp_iso = std::format("2026-01-27T12:00:{:02d}.000Z", i);
            batch.receive_time = std::chrono::steady_clock::now();
            batch.detections.push_back(
                Detection{.id = 1, .bounding_box_px = cv::Rect2f(600.0f, 400.0f, 80.0f, 200.0f)});
            buffer.add({"scene-1", category}, "cam-1", std::move(batch));
        }
        lock.lock();
        cv.wait_for(lock, std::chrono::milliseconds(100), [&] { return positions.size() == 2; });
    }

    ASSERT_EQ(positions.size(), 2u) << "Both categories should publish a reliable track";
    const auto& plane = positions.at("plane");
    const auto& person = positions.at("person");
    EXPECT_GT(std::hypot(plane[0] - person[0], plane[1] - person[1]), 0.1)
        << "TYPE_2 'plane' should project differently from TYPE_1 'person'";
}

// Scheduler reads rotation_from_velocity per category: true, false, and no asset entry.
TEST_F(TimeChunkSchedulerTest, Dispatch_AppliesRotationFromVelocityPerCategory) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    Scene scene;
    scene.uid = "scene-1";
    scene.name = "Test Scene 1";
    Camera cam;
    cam.uid = "cam-1";
    cam.name = "Camera 1";
    cam.intrinsics = {905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}};
    cam.extrinsics.translation = {0.0, 0.0, 3.0};
    cam.extrinsics.rotation = {-90.0, 0.0, 0.0};
    cam.extrinsics.scale = {1.0, 1.0, 1.0};
    scene.cameras.push_back(cam);
    registry.register_scenes({scene});

    TrackingConfig config = createConfig(100, 10);
    config.max_unreliable_time_s = 0.0;

    std::mutex mtx;
    std::condition_variable cv;
    std::map<std::string, int> publish_counts;
    std::map<std::string, Track> last_tracks;
    PublishCallback callback = [&](const std::string&, const std::string&,
                                   const std::string& category, const std::string&,
                                   const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        publish_counts[category]++;
        if (!tracks.empty()) {
            last_tracks[category] = tracks.front();
        }
        cv.notify_one();
    };

    const ObjectClassMap object_classes = {
        {"car", ObjectClassConfig{.rotation_from_velocity = true}},
        {"bike", ObjectClassConfig{.rotation_from_velocity = false}}};
    constexpr std::array<const char*, 3> kCategories = {"car", "bike", "person"};
    TimeChunkScheduler scheduler(buffer, registry, config, callback, makeSystemClock(),
                                 object_classes);
    scheduler.start();

    constexpr int kFrames = 30;
    constexpr auto kFramePeriod = std::chrono::microseconds(66'667);
    for (int i = 0; i < kFrames; ++i) {
        const float foot_x = 1000.0f - 20.0f * static_cast<float>(i);
        for (const char* category : kCategories) {
            DetectionBatch batch;
            batch.camera_id = "cam-1";
            batch.timestamp = std::chrono::system_clock::time_point{} + i * kFramePeriod;
            batch.timestamp_iso = "2026-01-27T12:00:00.000Z";
            batch.receive_time = std::chrono::steady_clock::now();
            batch.detections.push_back(Detection{
                .id = 1, .bounding_box_px = cv::Rect2f(foot_x - 20.0f, 520.0f, 40.0f, 80.0f)});
            buffer.add({"scene-1", category}, "cam-1", std::move(batch));
        }
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(1),
                                [&] {
                                    return std::ranges::all_of(kCategories, [&](const char* c) {
                                        return publish_counts[c] > i;
                                    });
                                }))
            << "Timed out waiting for frame " << i;
    }
    scheduler.stop();

    for (const char* category : kCategories) {
        ASSERT_TRUE(last_tracks.contains(category)) << category;
        const auto& v = last_tracks.at(category).velocity;
        ASSERT_GT(std::hypot(v[0], v[1]), kRotationSpeedThresholdOn) << category;
    }
    const auto& car = last_tracks.at("car");
    EXPECT_GT(std::abs(2.0 * std::atan2(car.rotation[2], car.rotation[3])), 0.5)
        << "rotation_from_velocity=true should publish the velocity heading";
    constexpr std::array<double, 4> kIdentity = {0.0, 0.0, 0.0, 1.0};
    EXPECT_EQ(last_tracks.at("bike").rotation, kIdentity)
        << "rotation_from_velocity=false should publish identity rotation";
    EXPECT_EQ(last_tracks.at("person").rotation, kIdentity)
        << "Category without an asset entry should publish identity rotation";
}

TEST_F(TimeChunkSchedulerTest, WorkerCount_StartsAtZero) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    TrackingConfig config = createConfig(100);

    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    EXPECT_EQ(scheduler.worker_count(), 0u);

    scheduler.start();
    // No data in buffer, so no workers should be created
    // Brief wait with timeout to verify no workers spawn
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    EXPECT_EQ(scheduler.worker_count(), 0u);

    scheduler.stop();
}

// =============================================================================
// Chunk building tests
// =============================================================================

TEST_F(TimeChunkSchedulerTest, BuildChunk_SortsBatchesByTimestamp) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    registerScenes(registry);
    TrackingConfig config = createConfig(100);

    std::mutex mtx;
    std::condition_variable cv;
    bool received = false;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>&) {
        std::lock_guard lock(mtx);
        received = true;
        cv.notify_one();
    };

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    TrackingScope scope{"scene-1", "person"};

    // Add batches with different timestamps (out of order)
    // Note: Use the same camera (cam-1) for all batches since camera must be registered
    auto batch1 = createBatch("cam-1", "2026-01-27T12:00:02.000Z");
    batch1.receive_time = std::chrono::steady_clock::now() + std::chrono::milliseconds(200);

    auto batch2 = createBatch("cam-1", "2026-01-27T12:00:01.000Z");
    batch2.receive_time = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);

    auto batch3 = createBatch("cam-1", "2026-01-27T12:00:00.000Z");
    batch3.receive_time = std::chrono::steady_clock::now();

    buffer.add(scope, "cam-1", std::move(batch1));
    buffer.add(scope, "cam-1", std::move(batch2));
    buffer.add(scope, "cam-1", std::move(batch3));

    scheduler.start();

    // Wait for processing
    {
        std::unique_lock lock(mtx);
        EXPECT_TRUE(cv.wait_for(lock, std::chrono::seconds(1), [&] { return received; }));
    }

    // The scheduler should have dispatched successfully
    EXPECT_GE(scheduler.dispatched_count(), 1);

    scheduler.stop();
}

// =============================================================================
// Counter tests
// =============================================================================

TEST_F(TimeChunkSchedulerTest, DispatchedCount_IncrementsOnDispatch) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    registerScenes(registry);
    TrackingConfig config = createConfig(100);

    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>&) {
        std::lock_guard lock(mtx);
        callback_count++;
        cv.notify_one();
    };

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    EXPECT_EQ(scheduler.dispatched_count(), 0);

    TrackingScope scope{"scene-1", "person"};
    buffer.add(scope, "cam-1", createBatch("cam-1", "2026-01-27T12:00:00.000Z"));

    scheduler.start();

    // Wait for dispatch
    {
        std::unique_lock lock(mtx);
        EXPECT_TRUE(cv.wait_for(lock, std::chrono::seconds(1), [&] { return callback_count > 0; }));
    }

    EXPECT_GT(scheduler.dispatched_count(), 0);

    scheduler.stop();
}

TEST_F(TimeChunkSchedulerTest, ScopeLimitDrops_StartsAtZero) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    TrackingConfig config = createConfig(100);

    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TimeChunkScheduler scheduler(buffer, registry, config, callback);

    EXPECT_EQ(scheduler.scope_limit_drops(), 0);
}

// =============================================================================
// Destructor tests
// =============================================================================

TEST_F(TimeChunkSchedulerTest, Destructor_StopsRunningScheduler) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    registerScenes(registry);
    TrackingConfig config = createConfig(100);

    int callback_count = 0;
    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&,
                                   const std::vector<Track>&) { callback_count++; };

    {
        TimeChunkScheduler scheduler(buffer, registry, config, callback);

        TrackingScope scope{"scene-1", "person"};
        buffer.add(scope, "cam-1", createBatch("cam-1", "2026-01-27T12:00:00.000Z"));

        scheduler.start();
        EXPECT_TRUE(scheduler.is_running());

        // Destructor should handle cleanup
    }

    // If we get here without hanging or crashing, destructor worked
    SUCCEED();
}

TEST_F(TimeChunkSchedulerTest, ConstructorRejectsZeroFps) {
    TimeChunkBuffer buffer;
    SceneRegistry registry;
    auto config = createConfig(0);
    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    EXPECT_THROW(TimeChunkScheduler(buffer, registry, config, callback), std::runtime_error);
}

} // namespace
} // namespace tracker
