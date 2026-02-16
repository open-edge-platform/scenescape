// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include "logger.hpp"
#include "time_chunk_buffer.hpp"

#include <thread>
#include <vector>

namespace tracker {
namespace {

class TimeChunkBufferTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }
};

// Test that empty buffer returns empty map
TEST_F(TimeChunkBufferTest, PopAll_EmptyBuffer_ReturnsEmpty) {
    TimeChunkBuffer buffer;

    EXPECT_TRUE(buffer.empty());
    EXPECT_EQ(buffer.scope_count(), 0);

    auto snapshot = buffer.pop_all();
    EXPECT_TRUE(snapshot.empty());
}

// Test adding single detection batch
TEST_F(TimeChunkBufferTest, Add_SingleBatch_CanBePopped) {
    TimeChunkBuffer buffer;

    TrackingScope scope{"scene-1", "person"};
    DetectionBatch batch;
    batch.camera_id = "cam-1";
    batch.timestamp_iso = "2026-01-27T12:00:00.000Z";
    batch.receive_time = std::chrono::steady_clock::now();
    batch.detections.push_back(Detection{.id = 1, .bounding_box_px = {10, 20, 50, 100}});

    buffer.add(scope, "cam-1", std::move(batch));

    EXPECT_FALSE(buffer.empty());
    EXPECT_EQ(buffer.scope_count(), 1);

    auto snapshot = buffer.pop_all();
    EXPECT_EQ(snapshot.size(), 1);
    EXPECT_TRUE(snapshot.contains(scope));
    EXPECT_EQ(snapshot[scope].size(), 1);
    EXPECT_TRUE(snapshot[scope].contains("cam-1"));
    EXPECT_EQ(snapshot[scope]["cam-1"].detections.size(), 1);

    // Buffer should be empty after pop_all
    EXPECT_TRUE(buffer.empty());
}

// Test keep-latest semantics: second add replaces first
TEST_F(TimeChunkBufferTest, Add_SameCameraScope_KeepsLatest) {
    TimeChunkBuffer buffer;

    TrackingScope scope{"scene-1", "person"};

    // First batch
    DetectionBatch batch1;
    batch1.camera_id = "cam-1";
    batch1.timestamp_iso = "2026-01-27T12:00:00.000Z";
    batch1.detections.push_back(Detection{.id = 1, .bounding_box_px = {10, 20, 50, 100}});
    buffer.add(scope, "cam-1", std::move(batch1));

    // Second batch for same camera/scope (should replace)
    DetectionBatch batch2;
    batch2.camera_id = "cam-1";
    batch2.timestamp_iso = "2026-01-27T12:00:01.000Z";
    batch2.detections.push_back(Detection{.id = 2, .bounding_box_px = {20, 30, 60, 110}});
    batch2.detections.push_back(Detection{.id = 3, .bounding_box_px = {30, 40, 70, 120}});
    buffer.add(scope, "cam-1", std::move(batch2));

    auto snapshot = buffer.pop_all();
    EXPECT_EQ(snapshot.size(), 1);
    EXPECT_EQ(snapshot[scope].size(), 1);

    // Should have the second batch (2 detections)
    const auto& final_batch = snapshot[scope]["cam-1"];
    EXPECT_EQ(final_batch.detections.size(), 2);
    EXPECT_EQ(final_batch.timestamp_iso, "2026-01-27T12:00:01.000Z");
}

// Test multiple scopes are kept separate
TEST_F(TimeChunkBufferTest, Add_MultipleScopes_KeptSeparate) {
    TimeChunkBuffer buffer;

    TrackingScope scope1{"scene-1", "person"};
    TrackingScope scope2{"scene-1", "vehicle"};
    TrackingScope scope3{"scene-2", "person"};

    DetectionBatch batch1;
    batch1.camera_id = "cam-1";
    buffer.add(scope1, "cam-1", std::move(batch1));

    DetectionBatch batch2;
    batch2.camera_id = "cam-1";
    buffer.add(scope2, "cam-1", std::move(batch2));

    DetectionBatch batch3;
    batch3.camera_id = "cam-2";
    buffer.add(scope3, "cam-2", std::move(batch3));

    EXPECT_EQ(buffer.scope_count(), 3);

    auto snapshot = buffer.pop_all();
    EXPECT_EQ(snapshot.size(), 3);
    EXPECT_TRUE(snapshot.contains(scope1));
    EXPECT_TRUE(snapshot.contains(scope2));
    EXPECT_TRUE(snapshot.contains(scope3));
}

// Test multiple cameras within same scope
TEST_F(TimeChunkBufferTest, Add_MultipleCamerasSameScope_AllKept) {
    TimeChunkBuffer buffer;

    TrackingScope scope{"scene-1", "person"};

    DetectionBatch batch1;
    batch1.camera_id = "cam-1";
    buffer.add(scope, "cam-1", std::move(batch1));

    DetectionBatch batch2;
    batch2.camera_id = "cam-2";
    buffer.add(scope, "cam-2", std::move(batch2));

    auto snapshot = buffer.pop_all();
    EXPECT_EQ(snapshot.size(), 1);
    EXPECT_EQ(snapshot[scope].size(), 2);
    EXPECT_TRUE(snapshot[scope].contains("cam-1"));
    EXPECT_TRUE(snapshot[scope].contains("cam-2"));
}

// Test thread safety with concurrent adds
TEST_F(TimeChunkBufferTest, Add_ConcurrentAdds_NoDataRace) {
    TimeChunkBuffer buffer;
    constexpr int NUM_THREADS = 4;
    constexpr int ADDS_PER_THREAD = 100;

    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&buffer, t]() {
            for (int i = 0; i < ADDS_PER_THREAD; ++i) {
                TrackingScope scope{"scene-" + std::to_string(t % 2), "category"};
                DetectionBatch batch;
                batch.camera_id = "cam-" + std::to_string(t);
                batch.detections.push_back(Detection{.id = i, .bounding_box_px = {}});
                buffer.add(scope, batch.camera_id, std::move(batch));
            }
        });
    }

    for (auto& thread : threads) {
        thread.join();
    }

    auto snapshot = buffer.pop_all();
    // Should have 2 scopes (scene-0 and scene-1)
    EXPECT_EQ(snapshot.size(), 2);

    // Each scope should have 2 cameras (even threads in one scope, odd in other)
    for (const auto& [scope, cameras] : snapshot) {
        EXPECT_EQ(cameras.size(), 2);
    }
}

// Test pop_all is atomic (clears buffer completely)
TEST_F(TimeChunkBufferTest, PopAll_ClearsBuffer) {
    TimeChunkBuffer buffer;

    TrackingScope scope{"scene-1", "person"};
    DetectionBatch batch;
    batch.camera_id = "cam-1";
    buffer.add(scope, "cam-1", std::move(batch));

    EXPECT_FALSE(buffer.empty());

    auto snapshot1 = buffer.pop_all();
    EXPECT_FALSE(snapshot1.empty());
    EXPECT_TRUE(buffer.empty());

    // Second pop should return empty
    auto snapshot2 = buffer.pop_all();
    EXPECT_TRUE(snapshot2.empty());
}

} // namespace
} // namespace tracker
