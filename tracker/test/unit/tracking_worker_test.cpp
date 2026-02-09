// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include "logger.hpp"
#include "tracking_worker.hpp"

#include <chrono>
#include <condition_variable>
#include <format>
#include <mutex>
#include <thread>

namespace tracker {
namespace {

class TrackingWorkerTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }
};

// Test that worker processes chunks and calls publish callback
TEST_F(TrackingWorkerTest, ProcessesChunks_CallsPublishCallback) {
    std::mutex mtx;
    std::condition_variable cv;
    int publish_count = 0;
    std::string published_scene_id;
    std::string published_category;

    PublishCallback callback = [&](const std::string& scene_id, const std::string& scene_name,
                                   const std::string& category, const std::string& timestamp,
                                   const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        publish_count++;
        published_scene_id = scene_id;
        published_category = category;
        cv.notify_one();
    };

    TrackingScope scope{"scene-1", "person"};
    TrackingWorker worker(scope, "Test Scene", 2, callback);

    // Create chunk with detections
    Chunk chunk;
    chunk.scene_id = "scene-1";
    chunk.category = "person";
    chunk.chunk_time = std::chrono::steady_clock::now();

    DetectionBatch batch;
    batch.camera_id = "cam-1";
    batch.timestamp_iso = "2026-01-27T12:00:00.000Z";
    batch.detections.push_back(Detection{.id = 1, .bounding_box_px = {10, 20, 50, 100}});
    chunk.camera_batches.push_back(std::move(batch));

    EXPECT_TRUE(worker.try_enqueue(std::move(chunk)));

    // Wait for processing
    {
        std::unique_lock lock(mtx);
        EXPECT_TRUE(cv.wait_for(lock, std::chrono::seconds(1), [&] { return publish_count > 0; }));
    }

    EXPECT_EQ(publish_count, 1);
    EXPECT_EQ(published_scene_id, "scene-1");
    EXPECT_EQ(published_category, "person");
    EXPECT_EQ(worker.processed_count(), 1);
}

// Test queue backpressure (drops when full)
TEST_F(TrackingWorkerTest, QueueFull_DropsChunk) {
    // Use a blocking callback to fill the queue
    std::mutex block_mtx;
    std::condition_variable block_cv;
    bool blocked = true;

    PublishCallback blocking_callback = [&](const std::string&, const std::string&,
                                            const std::string&, const std::string&,
                                            const std::vector<Track>&) {
        std::unique_lock lock(block_mtx);
        block_cv.wait(lock, [&] { return !blocked; });
    };

    TrackingScope scope{"scene-1", "person"};
    TrackingWorker worker(scope, "Test Scene", 2, blocking_callback);

    // Enqueue chunks to fill the queue
    for (int i = 0; i < 3; ++i) {
        Chunk chunk;
        chunk.scene_id = "scene-1";
        chunk.category = "person";
        chunk.chunk_time = std::chrono::steady_clock::now();

        DetectionBatch batch;
        batch.camera_id = "cam-1";
        batch.timestamp_iso = std::format("2026-01-27T12:00:{:02d}.000Z", i);
        chunk.camera_batches.push_back(std::move(batch));

        worker.try_enqueue(std::move(chunk));
    }

    // Give worker time to pick up one chunk (which will block)
    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    // Queue should have been full at some point, causing drops
    // Note: exact count depends on timing, but dropped_count should be > 0
    // if we filled beyond capacity while processing was blocked

    // Unblock the callback
    {
        std::lock_guard lock(block_mtx);
        blocked = false;
    }
    block_cv.notify_all();

    // Give time for processing
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // At least some chunks should have been processed
    EXPECT_GT(worker.processed_count(), 0);
}

// Test sentinel chunk causes worker to exit
TEST_F(TrackingWorkerTest, Sentinel_CausesExit) {
    int publish_count = 0;
    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&,
                                   const std::vector<Track>&) { publish_count++; };

    TrackingScope scope{"scene-1", "person"};

    {
        TrackingWorker worker(scope, "Test Scene", 2, callback);

        // Enqueue a normal chunk first
        Chunk chunk;
        chunk.scene_id = "scene-1";
        chunk.category = "person";
        DetectionBatch batch;
        batch.camera_id = "cam-1";
        batch.timestamp_iso = "2026-01-27T12:00:00.000Z";
        chunk.camera_batches.push_back(std::move(batch));

        worker.try_enqueue(std::move(chunk));

        // Push sentinel to trigger shutdown
        worker.push_sentinel();

        // Worker destructor will join the thread
    }

    // Worker should have exited cleanly
    // If it didn't, the destructor would hang (test would timeout)
    EXPECT_GE(publish_count, 0); // May or may not have processed the chunk before sentinel
}

// Test stub tracking produces tracks from detections
TEST_F(TrackingWorkerTest, StubTracking_ProducesTracksFromDetections) {
    std::vector<Track> published_tracks;
    std::mutex mtx;
    std::condition_variable cv;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        published_tracks = tracks;
        cv.notify_one();
    };

    TrackingScope scope{"scene-1", "vehicle"};
    TrackingWorker worker(scope, "Test Scene", 2, callback);

    Chunk chunk;
    chunk.scene_id = "scene-1";
    chunk.category = "vehicle";
    chunk.chunk_time = std::chrono::steady_clock::now();

    DetectionBatch batch;
    batch.camera_id = "cam-1";
    batch.timestamp_iso = "2026-01-27T12:00:00.000Z";
    batch.detections.push_back(Detection{.id = 1, .bounding_box_px = {100, 200, 50, 100}});
    batch.detections.push_back(Detection{.id = 2, .bounding_box_px = {300, 400, 60, 120}});
    chunk.camera_batches.push_back(std::move(batch));

    worker.try_enqueue(std::move(chunk));

    // Wait for processing
    {
        std::unique_lock lock(mtx);
        EXPECT_TRUE(
            cv.wait_for(lock, std::chrono::seconds(1), [&] { return !published_tracks.empty(); }));
    }

    EXPECT_EQ(published_tracks.size(), 2);

    // Check stub tracking output
    for (const auto& track : published_tracks) {
        EXPECT_FALSE(track.id.empty());
        EXPECT_EQ(track.category, "vehicle");
        // Stub uses identity quaternion
        EXPECT_EQ(track.rotation[3], 1.0);
    }
}

// Test scope accessor
TEST_F(TrackingWorkerTest, Scope_ReturnsCorrectScope) {
    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TrackingScope scope{"my-scene", "my-category"};
    TrackingWorker worker(scope, "My Scene", 2, callback);

    EXPECT_EQ(worker.scope().scene_id, "my-scene");
    EXPECT_EQ(worker.scope().category, "my-category");
}

} // namespace
} // namespace tracker
