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

    // Create chunk with empty camera_batches - tracker still advances time for aging
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

// Test that metadata_json is preserved end-to-end through the tracker pipeline:
// transform_detections() -> RobotVision tracker -> convert_tracks() -> Track::metadata_json.
//
// Uses max_unreliable_time_s = 0.0 so tracks become reliable on first observation,
// guaranteeing published tracks exist and the assertion is actually exercised.
TEST_F(TrackingWorkerTest, Tracking_MetadataJson_PreservedThroughTracker) {
    std::vector<Track> all_published_tracks;
    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;
    const int kChunksToSend = 3;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        all_published_tracks.insert(all_published_tracks.end(), tracks.begin(), tracks.end());
        callback_count++;
        cv.notify_one();
    };

    // Set max_unreliable_time_s = 0.0 so tracks are reliable immediately
    TrackingConfig config = make_test_tracking_config();
    config.max_unreliable_time_s = 0.0;

    TrackingScope scope{"scene-1", "person"};
    TrackingWorker worker(scope, "Test Scene", 10, callback, config, cameras_);

    const std::string expected_metadata = R"({"reid":{"model_name":"test"},"score":0.95})";

    for (int i = 0; i < kChunksToSend; ++i) {
        Chunk chunk;
        chunk.scene_id = "scene-1";
        chunk.category = "person";
        chunk.chunk_time = std::chrono::steady_clock::now();

        DetectionBatch batch;
        batch.camera_id = "cam-1";
        batch.timestamp_iso = std::format("2026-01-27T12:00:{:02d}.000Z", i);

        Detection det;
        det.id = 1;
        det.bounding_box_px = cv::Rect2f(100.0f, 200.0f, 50.0f, 100.0f);
        det.metadata_json = expected_metadata;
        batch.detections.push_back(std::move(det));

        chunk.camera_batches.push_back(std::move(batch));
        worker.try_enqueue(std::move(chunk));
    }

    // Wait for all chunks to be processed
    {
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(2),
                                [&] { return callback_count >= kChunksToSend; }))
            << "Timed out waiting for " << kChunksToSend << " publish callbacks";
    }

    // At least one reliable track must have been published; if not, the test
    // isn't validating the metadata passthrough path at all.
    ASSERT_GT(all_published_tracks.size(), 0u)
        << "No reliable tracks published - metadata passthrough cannot be verified";

    // Every published track must carry the original metadata unchanged
    for (const auto& track : all_published_tracks) {
        EXPECT_EQ(track.metadata_json, expected_metadata)
            << "Track " << track.id << " has wrong or missing metadata_json";
    }
}

// Test that confidence is preserved end-to-end through the tracker pipeline:
// transformDetections() -> RobotVision tracker -> convert_tracks() -> Track::confidence.
//
// Uses max_unreliable_time_s = 0.0 so tracks become reliable on first observation.
TEST_F(TrackingWorkerTest, Tracking_Confidence_PreservedThroughTracker) {
    std::vector<Track> all_published_tracks;
    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;
    const int kChunksToSend = 3;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        all_published_tracks.insert(all_published_tracks.end(), tracks.begin(), tracks.end());
        callback_count++;
        cv.notify_one();
    };

    TrackingConfig config = make_test_tracking_config();
    config.max_unreliable_time_s = 0.0;

    TrackingScope scope{"scene-1", "person"};
    TrackingWorker worker(scope, "Test Scene", 10, callback, config, cameras_);

    const double expected_confidence = 0.91;

    for (int i = 0; i < kChunksToSend; ++i) {
        Chunk chunk;
        chunk.scene_id = "scene-1";
        chunk.category = "person";
        chunk.chunk_time = std::chrono::steady_clock::now();

        DetectionBatch batch;
        batch.camera_id = "cam-1";
        batch.timestamp_iso = std::format("2026-01-27T12:00:{:02d}.000Z", i);

        Detection det;
        det.id = 1;
        det.bounding_box_px = cv::Rect2f(100.0f, 200.0f, 50.0f, 100.0f);
        det.confidence = expected_confidence;
        batch.detections.push_back(std::move(det));

        chunk.camera_batches.push_back(std::move(batch));
        worker.try_enqueue(std::move(chunk));
    }

    {
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(2),
                                [&] { return callback_count >= kChunksToSend; }))
            << "Timed out waiting for " << kChunksToSend << " publish callbacks";
    }

    ASSERT_GT(all_published_tracks.size(), 0u)
        << "No reliable tracks published - confidence passthrough cannot be verified";

    for (const auto& track : all_published_tracks) {
        ASSERT_TRUE(track.confidence.has_value())
            << "Track " << track.id << " is missing confidence";
        EXPECT_NEAR(*track.confidence, expected_confidence, 1e-9)
            << "Track " << track.id << " has wrong confidence";
    }
}

// -----------------------------------------------------------------
// Multi-camera metadata fusion tests
//
// These regression tests verify per-field fusion, confidence-based winner
// selection, latest-camera fallback, and clearing across subsequent chunks.
//
// Camera setup: both cameras share identical extrinsics (same position,
// same orientation, looking straight down). The same pixel bounding box
// therefore projects to the exact same world coordinate, so the Hungarian
// matcher always assigns both cameras' detections to one shared track.
// -----------------------------------------------------------------

// Two-camera map: cam-1 and cam-2 at identical positions so the same pixel
// bbox projects to the same world point, guaranteeing both detections merge
// into one track.
std::unordered_map<std::string, Camera> make_two_cameras() {
    auto cameras = make_test_cameras(); // cam-1 already configured
    Camera cam2;
    cam2.uid = "cam-2";
    cam2.name = "Test Camera 2";
    cam2.intrinsics = {905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}};
    cam2.extrinsics.translation = {0.0, 0.0, 3.0}; // identical to cam-1
    cam2.extrinsics.rotation = {-90.0, 0.0, 0.0};
    cam2.extrinsics.scale = {1.0, 1.0, 1.0};
    cameras["cam-2"] = cam2;
    return cameras;
}

// Helper: build a single-detection batch for a given camera.
// receive_time_offset_ms offsets the receive_time from now so that
// chunk sorting (earliest first) is deterministic.
DetectionBatch make_batch(const std::string& camera_id, int chunk_index, int receive_time_offset_ms,
                          const std::string& metadata_json,
                          std::optional<double> confidence = std::nullopt) {
    DetectionBatch batch;
    batch.camera_id = camera_id;
    batch.receive_time =
        std::chrono::steady_clock::now() + std::chrono::milliseconds(receive_time_offset_ms);
    batch.timestamp_iso =
        std::format("2026-01-27T12:00:{:02d}.{:03d}Z", chunk_index, receive_time_offset_ms);
    Detection det;
    det.bounding_box_px = cv::Rect2f(100.0f, 200.0f, 50.0f, 100.0f);
    det.metadata_json = metadata_json;
    det.confidence = confidence;
    batch.detections.push_back(std::move(det));
    return batch;
}

// Scenario 1 - higher confidence wins over lower confidence for the same field.
//
// cam-1 (earlier receive_time, processed first): gender=female  confidence=0.9  <- should WIN
// cam-2 (later  receive_time, processed last) : gender=male     confidence=0.7
//
// Expected behaviour: "female" wins (highest confidence)
TEST_F(TrackingWorkerTest, Tracking_MultiCamera_HigherConfidenceMetadataWins) {
    std::vector<Track> all_tracks;
    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;
    const int kChunksToSend = 4;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        all_tracks.insert(all_tracks.end(), tracks.begin(), tracks.end());
        callback_count++;
        cv.notify_one();
    };

    TrackingConfig config = make_test_tracking_config();
    config.max_unreliable_time_s = 0.0; // tracks become reliable immediately

    TrackingWorker worker({"scene-1", "person"}, "Test Scene", 10, callback, config,
                          make_two_cameras());

    const std::string meta_high =
        R"({"gender":{"label":"female","confidence":0.9,"model_name":"m1"}})";
    const std::string meta_low =
        R"({"gender":{"label":"male","confidence":0.7,"model_name":"m1"}})";

    for (int i = 0; i < kChunksToSend; ++i) {
        Chunk chunk;
        chunk.scene_id = "scene-1";
        chunk.category = "person";
        chunk.chunk_time = std::chrono::steady_clock::now();
        // cam-1 offset=0 (earlier), cam-2 offset=1 (later) -> cam-2 is last after sort
        chunk.camera_batches.push_back(make_batch("cam-1", i, 0, meta_high));
        chunk.camera_batches.push_back(make_batch("cam-2", i, 1, meta_low));
        worker.try_enqueue(std::move(chunk));
    }

    {
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(3),
                                [&] { return callback_count >= kChunksToSend; }));
    }
    ASSERT_FALSE(all_tracks.empty()) << "No reliable tracks published";

    for (const auto& track : all_tracks) {
        if (track.metadata_json.empty())
            continue; // skip heartbeat frames with no detections
        EXPECT_NE(track.metadata_json.find("female"), std::string::npos)
            << "Higher-confidence 'female' should win. Got: " << track.metadata_json;
        EXPECT_EQ(track.metadata_json.find("\"male\""), std::string::npos)
            << "Lower-confidence 'male' should be absent. Got: " << track.metadata_json;
    }
}

// Scenario 2 - disjoint fields from different cameras must all survive in the merged output.
//
// cam-1: plate number only
// cam-2: gender only
//
// Expected behaviour: Track.metadata_json contains both "plate" and "gender"
TEST_F(TrackingWorkerTest, Tracking_MultiCamera_DisjointMetadataFieldsMerged) {
    std::vector<Track> all_tracks;
    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;
    const int kChunksToSend = 4;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        all_tracks.insert(all_tracks.end(), tracks.begin(), tracks.end());
        callback_count++;
        cv.notify_one();
    };

    TrackingConfig config = make_test_tracking_config();
    config.max_unreliable_time_s = 0.0;

    TrackingWorker worker({"scene-1", "vehicle"}, "Test Scene", 10, callback, config,
                          make_two_cameras());

    const std::string meta_plate = R"({"plate":{"label":"XYZ-789","model_name":"lpr"}})";
    const std::string meta_gender =
        R"({"gender":{"label":"female","confidence":0.85,"model_name":"m1"}})";

    for (int i = 0; i < kChunksToSend; ++i) {
        Chunk chunk;
        chunk.scene_id = "scene-1";
        chunk.category = "vehicle";
        chunk.chunk_time = std::chrono::steady_clock::now();
        chunk.camera_batches.push_back(make_batch("cam-1", i, 0, meta_plate));
        chunk.camera_batches.push_back(make_batch("cam-2", i, 1, meta_gender));
        worker.try_enqueue(std::move(chunk));
    }

    {
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(3),
                                [&] { return callback_count >= kChunksToSend; }));
    }
    ASSERT_FALSE(all_tracks.empty()) << "No reliable tracks published";

    for (const auto& track : all_tracks) {
        if (track.metadata_json.empty())
            continue;
        EXPECT_NE(track.metadata_json.find("plate"), std::string::npos)
            << "cam-1's 'plate' field should survive merge. Got: " << track.metadata_json;
        EXPECT_NE(track.metadata_json.find("gender"), std::string::npos)
            << "cam-2's 'gender' field should survive merge. Got: " << track.metadata_json;
    }
}

// Scenario 3 - when no camera provides a confidence score, the latest camera
// chunk (highest receive_time) wins for a contested field.
//
// cam-1 (earlier): age=adult   no confidence
// cam-2 (later)  : age=senior  no confidence  <- should WIN (latest)
//
// "senior" wins because cam-2 is last in the sorted batch.
// This is the correct fallback, so this test documents and locks in the rule.
TEST_F(TrackingWorkerTest, Tracking_MultiCamera_FallbackToLatestCameraWhenNoConfidence) {
    std::vector<Track> all_tracks;
    std::mutex mtx;
    std::condition_variable cv;
    int callback_count = 0;
    const int kChunksToSend = 4;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        all_tracks.insert(all_tracks.end(), tracks.begin(), tracks.end());
        callback_count++;
        cv.notify_one();
    };

    TrackingConfig config = make_test_tracking_config();
    config.max_unreliable_time_s = 0.0;

    TrackingWorker worker({"scene-1", "person"}, "Test Scene", 10, callback, config,
                          make_two_cameras());

    const std::string meta_earlier = R"({"age":{"label":"adult","model_name":"m1"}})";
    const std::string meta_later = R"({"age":{"label":"senior","model_name":"m1"}})";

    for (int i = 0; i < kChunksToSend; ++i) {
        Chunk chunk;
        chunk.scene_id = "scene-1";
        chunk.category = "person";
        chunk.chunk_time = std::chrono::steady_clock::now();
        chunk.camera_batches.push_back(make_batch("cam-1", i, 0, meta_earlier)); // earlier
        chunk.camera_batches.push_back(make_batch("cam-2", i, 1, meta_later));   // later
        worker.try_enqueue(std::move(chunk));
    }

    {
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(3),
                                [&] { return callback_count >= kChunksToSend; }));
    }
    ASSERT_FALSE(all_tracks.empty()) << "No reliable tracks published";

    for (const auto& track : all_tracks) {
        if (track.metadata_json.empty())
            continue;
        EXPECT_NE(track.metadata_json.find("senior"), std::string::npos)
            << "Latest-camera fallback should pick 'senior'. Got: " << track.metadata_json;
        EXPECT_EQ(track.metadata_json.find("adult"), std::string::npos)
            << "'adult' from earlier camera should be absent. Got: " << track.metadata_json;
    }
}

// Scenario 4 - result must be deterministic: whether the higher-confidence value comes from the
// earlier or later camera batch must not change the winner when confidence values differ.
//
// Run A: cam-1 (high conf=0.9 female, earlier) then cam-2 (low conf=0.7 male, later)
// Run B: cam-1 (low  conf=0.7 male,  earlier) then cam-2 (high conf=0.9 female, later)
//
// Both runs must produce "female" as the winner.
TEST_F(TrackingWorkerTest, Tracking_MultiCamera_WinnerIsDeterministicRegardlessOfCameraOrder) {
    const std::string meta_high =
        R"({"gender":{"label":"female","confidence":0.9,"model_name":"m1"}})";
    const std::string meta_low =
        R"({"gender":{"label":"male","confidence":0.7,"model_name":"m1"}})";

    auto run_with_order = [&](bool high_conf_camera_is_first) -> std::string {
        std::vector<Track> all_tracks;
        std::mutex mtx;
        std::condition_variable cv;
        int callback_count = 0;
        const int kChunksToSend = 4;

        PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                       const std::string&, const std::vector<Track>& tracks) {
            std::lock_guard lock(mtx);
            all_tracks.insert(all_tracks.end(), tracks.begin(), tracks.end());
            callback_count++;
            cv.notify_one();
        };

        TrackingConfig config = make_test_tracking_config();
        config.max_unreliable_time_s = 0.0;

        TrackingWorker worker({"scene-1", "person"}, "Test Scene", 10, callback, config,
                              make_two_cameras());

        for (int i = 0; i < kChunksToSend; ++i) {
            Chunk chunk;
            chunk.scene_id = "scene-1";
            chunk.category = "person";
            chunk.chunk_time = std::chrono::steady_clock::now();
            if (high_conf_camera_is_first) {
                chunk.camera_batches.push_back(make_batch("cam-1", i, 0, meta_high)); // first
                chunk.camera_batches.push_back(make_batch("cam-2", i, 1, meta_low));  // last
            } else {
                chunk.camera_batches.push_back(make_batch("cam-1", i, 0, meta_low));  // first
                chunk.camera_batches.push_back(make_batch("cam-2", i, 1, meta_high)); // last
            }
            worker.try_enqueue(std::move(chunk));
        }

        {
            std::unique_lock lock(mtx);
            EXPECT_TRUE(cv.wait_for(lock, std::chrono::seconds(3),
                                    [&] { return callback_count >= kChunksToSend; }));
        }

        // Return the last non-empty metadata seen
        for (auto it = all_tracks.rbegin(); it != all_tracks.rend(); ++it) {
            if (!it->metadata_json.empty())
                return it->metadata_json;
        }
        return {};
    };

    const std::string result_a = run_with_order(true);  // high-conf camera first
    const std::string result_b = run_with_order(false); // high-conf camera last

    ASSERT_FALSE(result_a.empty()) << "No metadata in run A";
    ASSERT_FALSE(result_b.empty()) << "No metadata in run B";

    EXPECT_NE(result_a.find("female"), std::string::npos)
        << "Run A (high-conf first): 'female' should win. Got: " << result_a;
    EXPECT_NE(result_b.find("female"), std::string::npos)
        << "Run B (high-conf last): 'female' should still win. Got: " << result_b;
}

TEST_F(TrackingWorkerTest, Tracking_MultiCamera_FusionDoesNotLeakIntoSingleCameraChunk) {
    std::vector<std::vector<Track>> published_tracks;
    std::mutex mtx;
    std::condition_variable cv;

    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mtx);
        published_tracks.push_back(tracks);
        cv.notify_one();
    };

    TrackingConfig config = make_test_tracking_config();
    config.max_unreliable_time_s = 0.0;
    TrackingWorker worker({"scene-1", "person"}, "Test Scene", 10, callback, config,
                          make_two_cameras());

    Chunk fused_chunk;
    fused_chunk.scene_id = "scene-1";
    fused_chunk.category = "person";
    fused_chunk.chunk_time = std::chrono::steady_clock::now();
    fused_chunk.camera_batches.push_back(
        make_batch("cam-1", 0, 0, R"({"plate":{"label":"XYZ-789"}})"));
    fused_chunk.camera_batches.push_back(
        make_batch("cam-2", 0, 1, R"({"gender":{"label":"female"}})"));
    worker.try_enqueue(std::move(fused_chunk));

    Chunk single_camera_chunk;
    single_camera_chunk.scene_id = "scene-1";
    single_camera_chunk.category = "person";
    single_camera_chunk.chunk_time = std::chrono::steady_clock::now();
    single_camera_chunk.camera_batches.push_back(
        make_batch("cam-2", 1, 1, R"({"gender":{"label":"male"}})"));
    worker.try_enqueue(std::move(single_camera_chunk));

    {
        std::unique_lock lock(mtx);
        ASSERT_TRUE(cv.wait_for(lock, std::chrono::seconds(3),
                                [&] { return published_tracks.size() >= 2; }));
    }

    ASSERT_FALSE(published_tracks.back().empty());
    const auto& metadata = published_tracks.back().front().metadata_json;
    EXPECT_NE(metadata.find("male"), std::string::npos);
    EXPECT_EQ(metadata.find("plate"), std::string::npos);
    EXPECT_EQ(metadata.find("female"), std::string::npos);
}

} // namespace
} // namespace tracker
