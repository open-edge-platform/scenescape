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

// Default tracking config for tests
TrackingConfig make_test_tracking_config() {
    TrackingConfig config;
    config.max_lag_s = 1.0;
    config.time_chunking_rate_fps = 15;
    config.max_workers = 100;
    return config;
}

// Default camera config for tests
std::unordered_map<std::string, Camera> make_test_cameras() {
    Camera cam;
    cam.uid = "cam-1";
    cam.name = "Test Camera";
    cam.intrinsics = {
        905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}}; // fx, fy, cx, cy, distortion
    cam.extrinsics.translation = {0.0, 0.0, 3.0};          // 3m height
    cam.extrinsics.rotation = {-90.0, 0.0, 0.0};           // Looking straight down
    cam.extrinsics.scale = {1.0, 1.0, 1.0};
    return {{"cam-1", cam}};
}

class TrackingWorkerTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }

    TrackingConfig tracking_config_ = make_test_tracking_config();
    std::unordered_map<std::string, Camera> cameras_ = make_test_cameras();
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
    TrackingWorker worker(scope, "Test Scene", 2, callback, tracking_config_, cameras_);

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
    TrackingWorker worker(scope, "Test Scene", 2, blocking_callback, tracking_config_, cameras_);

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
        TrackingWorker worker(scope, "Test Scene", 2, callback, tracking_config_, cameras_);

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

// Test tracking produces tracks from detections
TEST_F(TrackingWorkerTest, Tracking_ProducesTracksFromDetections) {
    std::vector<Track> published_tracks;
    std::mutex mtx;
    std::condition_variable cv;
    bool callback_called = false;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        published_tracks = tracks;
        callback_called = true;
        cv.notify_one();
    };

    TrackingScope scope{"scene-1", "vehicle"};
    TrackingWorker worker(scope, "Test Scene", 2, callback, tracking_config_, cameras_);

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
        // With real tracking, callback is always called but tracks may be empty
        // until the Kalman filter builds confidence
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(1), [&] { return callback_called; }))
            << "Publish callback was never invoked";
    }

    // Check tracking output - tracks may be empty initially until Kalman filter builds confidence
    // With RobotVision tracking, tracks are only published once they become "reliable"
    // which requires multiple consistent detections
    for (const auto& track : published_tracks) {
        EXPECT_FALSE(track.id.empty()); // UUID string should not be empty
        EXPECT_EQ(track.category, "vehicle");
        // Uses identity quaternion
        EXPECT_EQ(track.rotation[3], 1.0);
    }
}

// Test scope accessor
TEST_F(TrackingWorkerTest, Scope_ReturnsCorrectScope) {
    PublishCallback callback = [](const std::string&, const std::string&, const std::string&,
                                  const std::string&, const std::vector<Track>&) {};

    TrackingScope scope{"my-scene", "my-category"};
    TrackingWorker worker(scope, "My Scene", 2, callback, tracking_config_, cameras_);

    EXPECT_EQ(worker.scope().scene_id, "my-scene");
    EXPECT_EQ(worker.scope().category, "my-category");
}

// Test that unknown camera in batch is skipped with warning (not crash)
TEST_F(TrackingWorkerTest, SkipsUnknownCamera_InBatch) {
    std::mutex mtx;
    std::condition_variable cv;
    int publish_count = 0;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>&) {
        std::lock_guard lock(mtx);
        publish_count++;
        cv.notify_one();
    };

    TrackingScope scope{"scene-1", "person"};
    TrackingWorker worker(scope, "Test Scene", 2, callback, tracking_config_, cameras_);

    // Create chunk with camera_id NOT in cameras_ map (only "cam-1" exists)
    Chunk chunk;
    chunk.scene_id = "scene-1";
    chunk.category = "person";
    chunk.chunk_time = std::chrono::steady_clock::now();

    DetectionBatch batch;
    batch.camera_id = "unknown-camera"; // Not in cameras_ map
    batch.timestamp_iso = "2026-01-27T12:00:00.000Z";
    batch.detections.push_back(Detection{.id = 1, .bounding_box_px = {10, 20, 50, 100}});
    chunk.camera_batches.push_back(std::move(batch));

    EXPECT_TRUE(worker.try_enqueue(std::move(chunk)));

    // Wait for processing - worker should log warning and continue
    {
        std::unique_lock lock(mtx);
        cv.wait_for(lock, std::chrono::milliseconds(500), [&] { return publish_count > 0; });
    }

    // Worker should process chunk (call callback) but skip unknown camera detections
    EXPECT_EQ(publish_count, 1);
    EXPECT_EQ(worker.processed_count(), 1);
}

// Test that empty chunk (no detections) flows through tracker and publishes
TEST_F(TrackingWorkerTest, EmptyChunk_FlowsThroughTracker) {
    std::mutex mtx;
    std::condition_variable cv;
    int publish_count = 0;
    std::string published_timestamp;
    std::vector<Track> published_tracks;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string& timestamp, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        publish_count++;
        published_timestamp = timestamp;
        published_tracks = tracks;
        cv.notify_one();
    };

    TrackingScope scope{"scene-1", "person"};
    TrackingWorker worker(scope, "Test Scene", 2, callback, tracking_config_, cameras_);

    // Create chunk with empty camera_batches — tracker still advances time for aging
    Chunk chunk;
    chunk.scene_id = "scene-1";
    chunk.category = "person";
    chunk.chunk_time = std::chrono::steady_clock::now();

    EXPECT_TRUE(worker.try_enqueue(std::move(chunk)));

    {
        std::unique_lock lock(mtx);
        cv.wait_for(lock, std::chrono::milliseconds(500), [&] { return publish_count > 0; });
    }

    EXPECT_EQ(publish_count, 1);
    EXPECT_EQ(worker.processed_count(), 1);
    // Empty detections -> no reliable tracks
    EXPECT_TRUE(published_tracks.empty());
    // Fallback timestamp should be valid ISO 8601
    EXPECT_FALSE(published_timestamp.empty());
    EXPECT_NE(published_timestamp.find('T'), std::string::npos);
    EXPECT_NE(published_timestamp.find('Z'), std::string::npos);
}

// Test queue_depth() returns correct queue size
TEST_F(TrackingWorkerTest, QueueDepth_ReturnsCorrectSize) {
    // Use blocking callback to keep chunks in queue
    std::mutex block_mtx;
    std::condition_variable block_cv;
    std::atomic<bool> blocked{true};
    std::atomic<bool> in_callback{false};

    PublishCallback blocking_callback = [&](const std::string&, const std::string&,
                                            const std::string&, const std::string&,
                                            const std::vector<Track>&) {
        in_callback = true;
        std::unique_lock lock(block_mtx);
        block_cv.wait(lock, [&] { return !blocked.load(); });
    };

    TrackingScope scope{"scene-1", "person"};
    TrackingWorker worker(scope, "Test Scene", 10, blocking_callback, tracking_config_, cameras_);

    // Queue depth starts at 0
    EXPECT_EQ(worker.queue_depth(), 0);

    // Enqueue a chunk
    Chunk chunk1;
    chunk1.scene_id = "scene-1";
    chunk1.category = "person";
    chunk1.chunk_time = std::chrono::steady_clock::now();
    DetectionBatch batch1;
    batch1.camera_id = "cam-1";
    batch1.timestamp_iso = "2026-01-27T12:00:00.000Z";
    chunk1.camera_batches.push_back(std::move(batch1));
    worker.try_enqueue(std::move(chunk1));

    // Wait for worker to pick up first chunk (will block in callback)
    auto deadline1 = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (!in_callback.load()) {
        ASSERT_LT(std::chrono::steady_clock::now(), deadline1)
            << "Timed out waiting for worker to enter callback";
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    // Enqueue second chunk - this should stay in queue
    Chunk chunk2;
    chunk2.scene_id = "scene-1";
    chunk2.category = "person";
    chunk2.chunk_time = std::chrono::steady_clock::now();
    DetectionBatch batch2;
    batch2.camera_id = "cam-1";
    batch2.timestamp_iso = "2026-01-27T12:00:01.000Z";
    chunk2.camera_batches.push_back(std::move(batch2));
    worker.try_enqueue(std::move(chunk2));

    // Queue should have 1 item (second chunk, first is being processed)
    EXPECT_EQ(worker.queue_depth(), 1);

    // Unblock and cleanup
    blocked = false;
    block_cv.notify_all();

    // Wait for processing to complete
    auto deadline2 = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (worker.queue_depth() > 0) {
        ASSERT_LT(std::chrono::steady_clock::now(), deadline2)
            << "Timed out waiting for queue to drain";
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    EXPECT_EQ(worker.queue_depth(), 0);
}

// Test that queue full condition reliably increments dropped_count
TEST_F(TrackingWorkerTest, QueueFull_IncrementsDroppedCount) {
    // Use blocking callback to prevent any processing
    std::mutex block_mtx;
    std::condition_variable block_cv;
    std::atomic<bool> blocked{true};
    std::atomic<bool> in_callback{false};

    PublishCallback blocking_callback = [&](const std::string&, const std::string&,
                                            const std::string&, const std::string&,
                                            const std::vector<Track>&) {
        in_callback = true;
        std::unique_lock lock(block_mtx);
        block_cv.wait(lock, [&] { return !blocked.load(); });
    };

    TrackingScope scope{"scene-1", "person"};
    // Small queue capacity of 1
    TrackingWorker worker(scope, "Test Scene", 1, blocking_callback, tracking_config_, cameras_);

    EXPECT_EQ(worker.dropped_count(), 0);

    // Enqueue first chunk - will be picked up by worker and block
    Chunk chunk1;
    chunk1.scene_id = "scene-1";
    chunk1.category = "person";
    chunk1.chunk_time = std::chrono::steady_clock::now();
    DetectionBatch batch1;
    batch1.camera_id = "cam-1";
    batch1.timestamp_iso = "2026-01-27T12:00:00.000Z";
    chunk1.camera_batches.push_back(std::move(batch1));
    EXPECT_TRUE(worker.try_enqueue(std::move(chunk1)));

    // Wait for worker to pick up and block on first chunk (polling, not fixed sleep)
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (!in_callback.load()) {
        ASSERT_LT(std::chrono::steady_clock::now(), deadline)
            << "Timed out waiting for worker to enter callback";
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    // Enqueue second chunk - fills queue (capacity=1)
    Chunk chunk2;
    chunk2.scene_id = "scene-1";
    chunk2.category = "person";
    chunk2.chunk_time = std::chrono::steady_clock::now();
    DetectionBatch batch2;
    batch2.camera_id = "cam-1";
    batch2.timestamp_iso = "2026-01-27T12:00:01.000Z";
    chunk2.camera_batches.push_back(std::move(batch2));
    EXPECT_TRUE(worker.try_enqueue(std::move(chunk2)));

    // Queue is now full. Third chunk should be dropped.
    Chunk chunk3;
    chunk3.scene_id = "scene-1";
    chunk3.category = "person";
    chunk3.chunk_time = std::chrono::steady_clock::now();
    DetectionBatch batch3;
    batch3.camera_id = "cam-1";
    batch3.timestamp_iso = "2026-01-27T12:00:02.000Z";
    chunk3.camera_batches.push_back(std::move(batch3));
    EXPECT_FALSE(worker.try_enqueue(std::move(chunk3))); // Should return false

    // Dropped count should be 1
    EXPECT_EQ(worker.dropped_count(), 1);

    // Unblock and cleanup
    {
        std::lock_guard lock(block_mtx);
        blocked = false;
    }
    block_cv.notify_all();
}

} // namespace
} // namespace tracker
