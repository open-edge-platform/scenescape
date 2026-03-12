// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "config_loader.hpp"
#include "logger.hpp"
#include "message_handler.hpp"
#include "mqtt_client.hpp"
#include "scene_registry.hpp"
#include "time_chunk_buffer.hpp"
#include "utils/json_schema_validator.hpp"

#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <chrono>
#include <filesystem>
#include <format>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

namespace tracker {
namespace {

using ::testing::_;
using ::testing::Invoke;
using ::testing::NiceMock;
using ::testing::Return;
using ::testing::StrictMock;

// Test scene constants
constexpr const char* TEST_SCENE_ID = "test-scene-001";
constexpr const char* TEST_SCENE_NAME = "Test Scene";
constexpr const char* TEST_CAMERA_ID = "cam1";

/**
 * @brief Create a SceneRegistry with a single test scene containing cam1.
 */
SceneRegistry createTestRegistry() {
    Camera cam;
    cam.uid = TEST_CAMERA_ID;
    cam.name = "Test Camera 1";
    cam.intrinsics.fx = 500.0;
    cam.intrinsics.fy = 500.0;
    cam.intrinsics.cx = 320.0;
    cam.intrinsics.cy = 240.0;
    // distortion defaults to 0.0 via struct initialization

    Scene scene;
    scene.uid = TEST_SCENE_ID;
    scene.name = TEST_SCENE_NAME;
    scene.cameras = {cam};

    SceneRegistry registry;
    registry.register_scenes({scene});
    return registry;
}

/**
 * @brief Generate ISO 8601 timestamp for a time in the past.
 *
 * Creates a UTC timestamp string (e.g., "2026-02-09T10:30:00.000Z") offset
 * from the current time. Useful for testing lag detection without hardcoded dates.
 *
 * @param offset Duration to subtract from current time
 * @return ISO 8601 formatted timestamp string
 */
std::string generate_past_iso_timestamp(std::chrono::seconds offset) {
    auto past_time =
        std::chrono::floor<std::chrono::seconds>(std::chrono::system_clock::now() - offset);
    return std::format("{:%Y-%m-%dT%H:%M:%S}.000Z", past_time);
}

/**
 * @brief Mock MQTT client for unit testing MessageHandler.
 */
class MockMqttClient : public IMqttClient {
public:
    MOCK_METHOD(void, connect, (), (override));
    MOCK_METHOD(void, disconnect, (std::chrono::milliseconds drain_timeout), (override));
    MOCK_METHOD(void, subscribe, (const std::string& topic), (override));
    MOCK_METHOD(void, unsubscribe, (const std::string& topic), (override));
    MOCK_METHOD(void, publish, (const std::string& topic, const std::string& payload), (override));
    MOCK_METHOD(void, setMessageCallback, (MessageCallback callback), (override));
    MOCK_METHOD(bool, isConnected, (), (const, override));
    MOCK_METHOD(bool, isSubscribed, (), (const, override));

    /**
     * @brief Capture the message callback for simulating incoming messages.
     */
    void captureCallback() {
        ON_CALL(*this, setMessageCallback(_)).WillByDefault(Invoke([this](MessageCallback cb) {
            captured_callback_ = std::move(cb);
        }));
    }

    /**
     * @brief Simulate receiving a message.
     */
    void simulateMessage(const std::string& topic, const std::string& payload) {
        if (captured_callback_) {
            captured_callback_(topic, payload);
        }
    }

    MessageCallback captured_callback_;
};

class MessageHandlerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize logger to avoid segfaults from LOG_* macros
        Logger::init("warn");

        mock_client_ = std::make_shared<NiceMock<MockMqttClient>>();
        mock_client_->captureCallback();
        ON_CALL(*mock_client_, isConnected()).WillByDefault(Return(true));
        ON_CALL(*mock_client_, isSubscribed()).WillByDefault(Return(true));

        // Create test scene registry with cam1
        test_registry_ = createTestRegistry();

        // Create tracking config with large max_lag to accept test timestamps from 2026
        // 315360000.0 = 10 years in seconds to accept any reasonable test timestamp
        test_config_ =
            TrackingConfig{.max_lag_s = 315360000.0, // 10 years - accept all test timestamps
                           .time_chunking_rate_fps = 15,
                           .max_workers = 50};
    }

    void TearDown() override { Logger::shutdown(); }

    std::shared_ptr<NiceMock<MockMqttClient>> mock_client_;
    SceneRegistry test_registry_;
    TimeChunkBuffer test_buffer_;
    TrackingConfig test_config_;
};

// Test that handler subscribes to each registered camera topic on start
TEST_F(MessageHandlerTest, Start_SubscribesToRegisteredCameras) {
    // test_registry_ has only cam1 registered
    EXPECT_CALL(*mock_client_, subscribe(std::format(MessageHandler::TOPIC_CAMERA_SUBSCRIBE_PATTERN,
                                                     TEST_CAMERA_ID)))
        .Times(1);

    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();
}

// Test subscribing to multiple cameras
TEST_F(MessageHandlerTest, Start_SubscribesToMultipleCameras) {
    // Create registry with multiple cameras
    Camera cam1, cam2;
    cam1.uid = "camera-1";
    cam1.name = "Camera 1";
    cam2.uid = "camera-2";
    cam2.name = "Camera 2";

    Scene scene;
    scene.uid = "multi-cam-scene";
    scene.name = "Multi Camera Scene";
    scene.cameras = {cam1, cam2};

    SceneRegistry multi_registry;
    multi_registry.register_scenes({scene});

    EXPECT_CALL(*mock_client_,
                subscribe(std::format(MessageHandler::TOPIC_CAMERA_SUBSCRIBE_PATTERN, "camera-1")))
        .Times(1);
    EXPECT_CALL(*mock_client_,
                subscribe(std::format(MessageHandler::TOPIC_CAMERA_SUBSCRIBE_PATTERN, "camera-2")))
        .Times(1);

    MessageHandler handler(mock_client_, multi_registry, test_buffer_, test_config_, false);
    handler.start();
}

// Test that handler does not subscribe when registry is empty
TEST_F(MessageHandlerTest, Start_NoSubscriptionsWithEmptyRegistry) {
    SceneRegistry empty_registry;

    // No subscribe calls expected
    EXPECT_CALL(*mock_client_, subscribe(_)).Times(0);

    MessageHandler handler(mock_client_, empty_registry, test_buffer_, test_config_, false);
    handler.start();
}

// Test that handler sets message callback on start
TEST_F(MessageHandlerTest, Start_SetsMessageCallback) {
    EXPECT_CALL(*mock_client_, setMessageCallback(_)).Times(1);

    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();
}

// Test processing valid camera message increments received count
TEST_F(MessageHandlerTest, HandleMessage_IncrementsReceivedCount) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    EXPECT_EQ(handler.getReceivedCount(), 0);

    // Valid camera message
    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
}

// Test processing valid message buffers detections
TEST_F(MessageHandlerTest, HandleMessage_BuffersDetections) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getBufferedCount(), 1);

    // Verify buffer contains the expected data
    auto buffer_data = test_buffer_.pop_all();
    ASSERT_EQ(buffer_data.size(), 1);

    TrackingScope expected_scope{"test-scene-001", "person"};
    ASSERT_TRUE(buffer_data.count(expected_scope) == 1);

    const auto& camera_map = buffer_data.at(expected_scope);
    ASSERT_EQ(camera_map.size(), 1);
    ASSERT_TRUE(camera_map.count("cam1") == 1);

    const auto& batch = camera_map.at("cam1");
    EXPECT_EQ(batch.camera_id, "cam1");
    EXPECT_EQ(batch.timestamp_iso, "2026-01-27T12:00:00.000Z");
    ASSERT_EQ(batch.detections.size(), 1);
    EXPECT_EQ(batch.detections[0].id, 1);
}

// Test buffered data contains correct detection info
TEST_F(MessageHandlerTest, BufferedData_ContainsCorrectDetectionInfo) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string input_payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", input_payload);

    // Verify buffer has correct structure
    auto buffer_data = test_buffer_.pop_all();
    ASSERT_EQ(buffer_data.size(), 1);

    TrackingScope expected_scope{"test-scene-001", "person"};
    const auto& batch = buffer_data.at(expected_scope).at("cam1");

    EXPECT_EQ(batch.camera_id, "cam1");
    EXPECT_EQ(batch.timestamp_iso, "2026-01-27T12:00:00.000Z");
    ASSERT_EQ(batch.detections.size(), 1);

    const auto& det = batch.detections[0];
    EXPECT_EQ(det.bounding_box_px.x, 10);
    EXPECT_EQ(det.bounding_box_px.y, 20);
    EXPECT_EQ(det.bounding_box_px.width, 50);
    EXPECT_EQ(det.bounding_box_px.height, 100);
}

// Test that invalid JSON is rejected
TEST_F(MessageHandlerTest, HandleMessage_RejectsInvalidJson) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string invalid_json = "{ this is not valid json }";
    mock_client_->simulateMessage("scenescape/data/camera/cam1", invalid_json);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getBufferedCount(), 0);
}

// Test that empty objects map still produces output
TEST_F(MessageHandlerTest, HandleMessage_AcceptsEmptyObjects) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    // First empty message: no active scopes yet, so nothing buffered
    EXPECT_EQ(handler.getBufferedCount(), 0);
}

// Test that empty/partial messages produce empty batches for all previously seen scopes.
//
// Exercises three scenarios in sequence using the same accumulated active-scope state:
//   1. Single scope: 'person' seen first; an empty message produces an empty batch for it.
//   2. Multiple scopes: after 'car' is introduced, an empty message produces empty batches
//      for both 'person' and 'car'.
//   3. Partial message: a message that contains only 'person' detections still produces an
//      empty batch for 'car', enabling Kalman filter aging for the absent category.
TEST_F(MessageHandlerTest, EmptyObjects_AfterNonEmpty_CreatesEmptyBatchForPreviousScope) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    TrackingScope person_scope{"test-scene-001", "person"};
    TrackingScope car_scope{"test-scene-001", "car"};

    // --- Scenario 1: single known scope ---
    // First message: establishes "person" scope; verify scope is registered with 1 detection.
    mock_client_->simulateMessage("scenescape/data/camera/cam1", R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })");
    {
        auto first_data = test_buffer_.pop_all();
        ASSERT_EQ(first_data.size(), 1u);
        ASSERT_EQ(first_data.count(person_scope), 1u);
        EXPECT_EQ(first_data.at(person_scope).at("cam1").detections.size(), 1u);
    }

    // Empty message: should produce an empty batch for "person" (enables track aging)
    mock_client_->simulateMessage("scenescape/data/camera/cam1", R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:01.000Z",
        "objects": {}
    })");
    {
        auto buffer_data = test_buffer_.pop_all();
        ASSERT_EQ(buffer_data.size(), 1u);
        ASSERT_EQ(buffer_data.count(person_scope), 1u);
        const auto& batch = buffer_data.at(person_scope).at("cam1");
        EXPECT_EQ(batch.camera_id, "cam1");
        EXPECT_TRUE(batch.detections.empty()); // Empty batch enables Kalman filter time-step
    }

    // --- Scenario 2: two known scopes, empty message ---
    // Introduce "car" scope alongside "person"
    mock_client_->simulateMessage("scenescape/data/camera/cam1", R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:02.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}],
            "car":    [{"id": 2, "bounding_box_px": {"x": 200, "y": 300, "width": 80, "height": 60}}]
        }
    })");
    auto _ = test_buffer_.pop_all(); // drain

    // Empty message: should produce empty batches for both "person" and "car"
    mock_client_->simulateMessage("scenescape/data/camera/cam1", R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:03.000Z",
        "objects": {}
    })");
    {
        auto buffer_data = test_buffer_.pop_all();
        ASSERT_EQ(buffer_data.size(), 2u);
        ASSERT_EQ(buffer_data.count(person_scope), 1u);
        ASSERT_EQ(buffer_data.count(car_scope), 1u);
        EXPECT_TRUE(buffer_data.at(person_scope).at("cam1").detections.empty());
        EXPECT_TRUE(buffer_data.at(car_scope).at("cam1").detections.empty());
    }

    // --- Scenario 3: partial message with two known scopes ---
    // A message that only contains "person" detections should still produce an empty batch
    // for "car", ensuring that the absent category is aged by the Kalman filter.
    mock_client_->simulateMessage("scenescape/data/camera/cam1", R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:04.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })");
    {
        auto buffer_data = test_buffer_.pop_all();
        ASSERT_EQ(buffer_data.size(), 2u);
        ASSERT_EQ(buffer_data.count(person_scope), 1u);
        ASSERT_EQ(buffer_data.count(car_scope), 1u);
        EXPECT_FALSE(buffer_data.at(person_scope).at("cam1").detections.empty()); // has detections
        EXPECT_TRUE(buffer_data.at(car_scope).at("cam1").detections.empty());     // empty batch
    }
}

// Test multiple objects categories are parsed correctly
TEST_F(MessageHandlerTest, HandleMessage_ParsesMultipleCategories) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [
                {"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}},
                {"id": 2, "bounding_box_px": {"x": 100, "y": 200, "width": 60, "height": 120}}
            ],
            "vehicle": [
                {"id": 3, "bounding_box_px": {"x": 300, "y": 400, "width": 150, "height": 80}}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    // Now publishes once per category
    EXPECT_EQ(handler.getBufferedCount(), 2);
}

// Test detection without id is valid (id is optional)
TEST_F(MessageHandlerTest, HandleMessage_AcceptsDetectionWithoutId) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [
                {"bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getBufferedCount(), 1);
}

// Test buffered data preserves timestamp from input
TEST_F(MessageHandlerTest, BufferedData_PreservesTimestamp) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string expected_timestamp = "2026-01-27T15:45:30.123Z";
    std::string input_payload = R"({
        "id": "cam1",
        "timestamp": ")" + expected_timestamp +
                                R"(",
        "objects": {"person": [{"bounding_box_px": {"x": 0, "y": 0, "width": 10, "height": 20}}]}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", input_payload);

    auto buffer_data = test_buffer_.pop_all();
    ASSERT_EQ(buffer_data.size(), 1);

    TrackingScope expected_scope{"test-scene-001", "person"};
    const auto& batch = buffer_data.at(expected_scope).at("cam1");
    EXPECT_EQ(batch.timestamp_iso, expected_timestamp);
}

// Test that stop() can be called safely
TEST_F(MessageHandlerTest, Stop_CanBeCalled) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();
    handler.stop(); // Should not throw
    SUCCEED();
}

// Test that lagged messages are dropped (timestamp older than max_lag_s)
TEST_F(MessageHandlerTest, HandleMessage_DropsLaggedMessages) {
    // Use very small max_lag (1ms) - any timestamp more than 1ms old is considered lagged
    TrackingConfig lag_config{.max_lag_s = 0.001, .time_chunking_rate_fps = 15, .max_workers = 100};

    MessageHandler handler(mock_client_, test_registry_, test_buffer_, lag_config, false);
    handler.start();

    EXPECT_EQ(handler.getLaggedCount(), 0);

    // Generate timestamp 1 hour in the past - guaranteed to exceed 1ms max_lag threshold
    std::string past_timestamp = generate_past_iso_timestamp(std::chrono::hours(1));
    std::string payload = std::format(R"({{
        "id": "cam1",
        "timestamp": "{}",
        "objects": {{
            "person": [{{"id": 1, "bounding_box_px": {{"x": 10, "y": 20, "width": 50, "height": 100}}}}]
        }}
    }})",
                                      past_timestamp);

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getLaggedCount(), 1);
    EXPECT_EQ(handler.getBufferedCount(), 0); // Message dropped, not buffered
    EXPECT_EQ(handler.getRejectedCount(), 0); // Not rejected, just lagged
}

// Test that unknown camera messages are rejected
TEST_F(MessageHandlerTest, HandleMessage_RejectsUnknownCamera) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    // unknown-cam is not in the test registry (only cam1 is registered)
    std::string payload = R"({
        "id": "unknown-cam",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/unknown-cam", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getBufferedCount(), 0);
}

// Test handler with schema validation disabled accepts all valid JSON
TEST_F(MessageHandlerTest, SchemaValidationDisabled_AcceptsValidJson) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_,
                           false); // schema_validation = false
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {"person": [{"bounding_box_px": {"x": 0, "y": 0, "width": 10, "height": 20}}]}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getRejectedCount(), 0);
}

// Test that multiple categories result in separate buffer entries
TEST_F(MessageHandlerTest, MultipleCategories_CreateSeparateBufferEntries) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string input_payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 0, "y": 0, "width": 10, "height": 20}}],
            "vehicle": [{"id": 2, "bounding_box_px": {"x": 100, "y": 100, "width": 50, "height": 30}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", input_payload);

    EXPECT_EQ(handler.getBufferedCount(), 2); // One per category

    auto buffer_data = test_buffer_.pop_all();
    ASSERT_EQ(buffer_data.size(), 2);

    TrackingScope person_scope{"test-scene-001", "person"};
    TrackingScope vehicle_scope{"test-scene-001", "vehicle"};

    EXPECT_TRUE(buffer_data.count(person_scope) == 1);
    EXPECT_TRUE(buffer_data.count(vehicle_scope) == 1);
}

// Test that buffer keeps latest data when same camera sends multiple messages
TEST_F(MessageHandlerTest, BufferKeepsLatest_WhenSameCameraSendsMultiple) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    // First message with id=1
    std::string first_payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {"person": [{"id": 1, "bounding_box_px": {"x": 100, "y": 50, "width": 80, "height": 200}}]}
    })";

    // Second message with id=2
    std::string second_payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.100Z",
        "objects": {"person": [{"id": 2, "bounding_box_px": {"x": 200, "y": 100, "width": 60, "height": 150}}]}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", first_payload);
    mock_client_->simulateMessage("scenescape/data/camera/cam1", second_payload);

    EXPECT_EQ(handler.getBufferedCount(), 2); // Both buffered

    auto buffer_data = test_buffer_.pop_all();
    TrackingScope expected_scope{"test-scene-001", "person"};

    // Buffer should have only one entry per scope+camera (keep-latest semantics)
    ASSERT_EQ(buffer_data.size(), 1);
    const auto& batch = buffer_data.at(expected_scope).at("cam1");

    // Should have the LATEST detection (id=2)
    ASSERT_EQ(batch.detections.size(), 1);
    EXPECT_EQ(batch.detections[0].id, 2);
    EXPECT_EQ(batch.timestamp_iso, "2026-01-27T12:00:00.100Z");
}

//
// Parameterized tests for malformed detection handling
//

struct MalformedDetectionTestCase {
    std::string name;
    std::string payload;
    bool expect_buffered; // true if empty batch should still be buffered
};

void PrintTo(const MalformedDetectionTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class MalformedDetectionTest : public MessageHandlerTest,
                               public ::testing::WithParamInterface<MalformedDetectionTestCase> {};

TEST_P(MalformedDetectionTest, SkipsMalformedDetectionAndNoPublish) {
    const auto& tc = GetParam();
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    mock_client_->simulateMessage("scenescape/data/camera/cam1", tc.payload);

    // Message is received and processed (malformed detections skipped)
    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0); // Message not rejected

    if (tc.expect_buffered) {
        // Category exists but all detections were malformed -> empty batch buffered
        // (tracker still needs the heartbeat for track aging)
        EXPECT_EQ(handler.getBufferedCount(), 1);
        auto buffer_data = test_buffer_.pop_all();
        TrackingScope scope{"test-scene-001", "person"};
        ASSERT_TRUE(buffer_data.count(scope));
        EXPECT_TRUE(buffer_data.at(scope).at("cam1").detections.empty());
    } else {
        // Category itself was invalid (not an array) -> nothing buffered
        EXPECT_EQ(handler.getBufferedCount(), 0);
    }
}

INSTANTIATE_TEST_SUITE_P(
    MalformedDetections, MalformedDetectionTest,
    ::testing::Values(
        MalformedDetectionTestCase{
            "MissingBoundingBoxHeight",
            R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z", "objects": {"person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50}}]}})",
            true},
        MalformedDetectionTestCase{
            "NoBoundingBox",
            R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z", "objects": {"person": [{"id": 1}]}})",
            true},
        MalformedDetectionTestCase{
            "BoundingBoxIsString",
            R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z", "objects": {"person": [{"id": 1, "bounding_box_px": "not_an_object"}]}})",
            true},
        MalformedDetectionTestCase{
            "BoundingBoxIsArray",
            R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z", "objects": {"person": [{"id": 1, "bounding_box_px": [10, 20, 50, 100]}]}})",
            true},
        MalformedDetectionTestCase{
            "CategoryIsNotArray",
            R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z", "objects": {"person": "not_an_array"}})",
            false},
        MalformedDetectionTestCase{
            "DetectionIsNotObject",
            R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z", "objects": {"person": ["not_an_object", 123, null]}})",
            true}),
    [](const ::testing::TestParamInfo<MalformedDetectionTestCase>& info) {
        return info.param.name;
    });

//
// Parameterized tests for invalid topic rejection
//

struct InvalidTopicTestCase {
    std::string name;
    std::string topic;
};

void PrintTo(const InvalidTopicTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class InvalidTopicTest : public MessageHandlerTest,
                         public ::testing::WithParamInterface<InvalidTopicTestCase> {};

TEST_P(InvalidTopicTest, RejectsInvalidTopic) {
    const auto& tc = GetParam();
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    std::string payload =
        R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z", "objects": {}})";
    mock_client_->simulateMessage(tc.topic, payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
}

INSTANTIATE_TEST_SUITE_P(
    InvalidTopics, InvalidTopicTest,
    ::testing::Values(InvalidTopicTestCase{"EmptyCameraId", "scenescape/data/camera/"},
                      InvalidTopicTestCase{"WrongTopicPrefix", "other/topic/cam1"},
                      InvalidTopicTestCase{"TooShortTopic", "scenescape/data"},
                      InvalidTopicTestCase{"WrongPrefix", "wrongprefix/data/camera/cam1"}),
    [](const ::testing::TestParamInfo<InvalidTopicTestCase>& info) { return info.param.name; });

//
// Parameterized tests for required field validation
// (consolidates: RejectsMissingFields, RejectsMissingId, RejectsNonStringId,
// RejectsNonStringTimestamp)
//

struct InvalidFieldTestCase {
    std::string name;
    std::string payload;
};

void PrintTo(const InvalidFieldTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class InvalidFieldTest : public MessageHandlerTest,
                         public ::testing::WithParamInterface<InvalidFieldTestCase> {};

TEST_P(InvalidFieldTest, RejectsInvalidFields) {
    const auto& tc = GetParam();
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    mock_client_->simulateMessage("scenescape/data/camera/cam1", tc.payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getBufferedCount(), 0);
}

INSTANTIATE_TEST_SUITE_P(
    InvalidFields, InvalidFieldTest,
    ::testing::Values(
        InvalidFieldTestCase{"MissingObjects",
                             R"({"id": "cam1", "timestamp": "2026-01-27T12:00:00.000Z"})"},
        InvalidFieldTestCase{"MissingId",
                             R"({"timestamp": "2026-01-27T12:00:00.000Z", "objects": {}})"},
        InvalidFieldTestCase{
            "NonStringId",
            R"({"id": 123, "timestamp": "2026-01-27T12:00:00.000Z", "objects": {}})"},
        InvalidFieldTestCase{"NonStringTimestamp",
                             R"({"id": "cam1", "timestamp": 1234567890, "objects": {}})"}),
    [](const ::testing::TestParamInfo<InvalidFieldTestCase>& info) { return info.param.name; });

//
// Schema validation tests (covers lines 37-79, 144-159, 216-265)
//

/**
 * @brief Get path to schema directory.
 */
std::filesystem::path get_schema_dir() {
    const auto this_file = std::filesystem::weakly_canonical(std::filesystem::path(__FILE__));
    const auto project_root = this_file.parent_path().parent_path().parent_path();
    return project_root / "schema";
}

// Test valid message passes schema validation (also verifies schemas load correctly)
TEST_F(MessageHandlerTest, SchemaValidation_AcceptsValidMessage) {
    auto schema_dir = get_schema_dir();
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, true,
                           schema_dir);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [
                {"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getBufferedCount(), 1);
}

// Test invalid message is rejected by schema validation
TEST_F(MessageHandlerTest, SchemaValidation_RejectsInvalidMessage) {
    auto schema_dir = get_schema_dir();
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, true,
                           schema_dir);
    handler.start();

    // Missing required "timestamp" field
    std::string payload = R"({
        "id": "cam1",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getBufferedCount(), 0);
}

// Test schema gracefully falls back when schema directory is invalid or missing
TEST_F(MessageHandlerTest, SchemaValidation_GracefulFallbackOnErrors) {
    // Non-existent schema directory - should not throw, just log warning
    std::filesystem::path bad_dir = "/nonexistent/schema/dir";
    EXPECT_NO_THROW({
        MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, true,
                               bad_dir);
        handler.start();

        // Without schemas loaded, messages should still be processed
        std::string payload = R"({
            "id": "cam1",
            "timestamp": "2026-01-27T12:00:00.000Z",
            "objects": {"person": [{"bounding_box_px": {"x": 0, "y": 0, "width": 10, "height": 20}}]}
        })";
        mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);
    });
}

//
// Dynamic mode (database update) tests
//

// Test that dynamic mode subscribes to database update topic on start
TEST_F(MessageHandlerTest, DynamicMode_SubscribesToDatabaseUpdateTopic) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);

    bool callback_called = false;
    handler.enableDynamicMode([&callback_called]() { callback_called = true; });

    // Expect subscription to both camera and database update topics
    EXPECT_CALL(*mock_client_, subscribe(std::format(MessageHandler::TOPIC_CAMERA_SUBSCRIBE_PATTERN,
                                                     TEST_CAMERA_ID)))
        .Times(1);
    EXPECT_CALL(*mock_client_, subscribe(std::string(MessageHandler::TOPIC_DATABASE_UPDATE)))
        .Times(1);

    handler.start();
}

// Test that static mode does NOT subscribe to database update topic
TEST_F(MessageHandlerTest, StaticMode_NoDatabaseUpdateSubscription) {
    // Only camera subscription expected, no database update subscription
    EXPECT_CALL(*mock_client_, subscribe(std::format(MessageHandler::TOPIC_CAMERA_SUBSCRIBE_PATTERN,
                                                     TEST_CAMERA_ID)))
        .Times(1);
    EXPECT_CALL(*mock_client_, subscribe(std::string(MessageHandler::TOPIC_DATABASE_UPDATE)))
        .Times(0);

    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();
}

// Test dynamic mode with multiple scenes still subscribes to single database update topic
TEST_F(MessageHandlerTest, DynamicMode_SingleDatabaseSubscriptionForMultipleScenes) {
    Camera cam1, cam2;
    cam1.uid = "cam-a";
    cam1.name = "Camera A";
    cam2.uid = "cam-b";
    cam2.name = "Camera B";

    Scene scene1;
    scene1.uid = "scene-alpha";
    scene1.name = "Scene Alpha";
    scene1.cameras = {cam1};

    Scene scene2;
    scene2.uid = "scene-beta";
    scene2.name = "Scene Beta";
    scene2.cameras = {cam2};

    SceneRegistry multi_registry;
    multi_registry.register_scenes({scene1, scene2});

    // Allow camera topic subscriptions
    EXPECT_CALL(*mock_client_, subscribe(::testing::_)).Times(::testing::AnyNumber());
    // Exactly one database update subscription regardless of scene count
    EXPECT_CALL(*mock_client_, subscribe(std::string(MessageHandler::TOPIC_DATABASE_UPDATE)))
        .Times(1);

    MessageHandler handler(mock_client_, multi_registry, test_buffer_, test_config_, false);
    handler.enableDynamicMode([]() {});
    handler.start();
}

// Test that receiving a database update message triggers the shutdown callback
TEST_F(MessageHandlerTest, DynamicMode_DatabaseUpdateTriggersShutdown) {
    bool callback_called = false;
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.enableDynamicMode([&callback_called]() { callback_called = true; });
    handler.start();

    EXPECT_FALSE(callback_called);

    mock_client_->simulateMessage(MessageHandler::TOPIC_DATABASE_UPDATE, "update");

    EXPECT_TRUE(callback_called);
}

// Test that database update messages don't increment camera message counters
TEST_F(MessageHandlerTest, DynamicMode_DatabaseUpdateDoesNotIncrementCounters) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.enableDynamicMode([]() {});
    handler.start();

    mock_client_->simulateMessage(MessageHandler::TOPIC_DATABASE_UPDATE, "update");

    EXPECT_EQ(handler.getReceivedCount(), 0);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getBufferedCount(), 0);
}

// Test that camera messages still work normally in dynamic mode
TEST_F(MessageHandlerTest, DynamicMode_CameraMessagesStillWork) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.enableDynamicMode([]() {});
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getBufferedCount(), 1);
}

// Test that stop() unsubscribes from database update topic in dynamic mode
TEST_F(MessageHandlerTest, DynamicMode_StopUnsubscribesFromDatabaseUpdateTopic) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.enableDynamicMode([]() {});
    handler.start();

    // Allow camera topic unsubscriptions (catch-all must precede specific expectation)
    EXPECT_CALL(*mock_client_, unsubscribe(::testing::_)).Times(::testing::AnyNumber());
    EXPECT_CALL(*mock_client_, unsubscribe(std::string(MessageHandler::TOPIC_DATABASE_UPDATE)))
        .Times(1);

    handler.stop();
}

// Test that stop() in static mode does NOT unsubscribe from database update topic
TEST_F(MessageHandlerTest, StaticMode_StopDoesNotUnsubscribeDatabaseUpdate) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    // Allow camera topic unsubscriptions (catch-all must precede specific expectation)
    EXPECT_CALL(*mock_client_, unsubscribe(::testing::_)).Times(::testing::AnyNumber());
    EXPECT_CALL(*mock_client_, unsubscribe(std::string(MessageHandler::TOPIC_DATABASE_UPDATE)))
        .Times(0);

    handler.stop();
}

// Test that database update in static mode is treated as camera message (rejected)
TEST_F(MessageHandlerTest, StaticMode_DatabaseUpdateTreatedAsCameraMessage) {
    MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, false);
    handler.start();

    // In static mode, database update topic is routed to handleCameraMessage
    // which rejects it because it doesn't match camera topic format
    mock_client_->simulateMessage(MessageHandler::TOPIC_DATABASE_UPDATE, "update");

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
}

//
// Schema file edge case test with temp directory
//

class SchemaFileTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::init("warn");
        mock_client_ = std::make_shared<NiceMock<MockMqttClient>>();
        mock_client_->captureCallback();
        ON_CALL(*mock_client_, isConnected()).WillByDefault(Return(true));
        ON_CALL(*mock_client_, isSubscribed()).WillByDefault(Return(true));

        // Create temp directory for test schemas
        temp_dir_ = std::filesystem::temp_directory_path() / "schema_test";
        std::filesystem::create_directories(temp_dir_);

        // Create test scene registry
        test_registry_ = createTestRegistry();

        // Create tracking config with large max_lag to accept test timestamps from 2026
        test_config_ =
            TrackingConfig{.max_lag_s = 315360000.0, // 10 years - accept all test timestamps
                           .time_chunking_rate_fps = 15,
                           .max_workers = 50};
    }

    void TearDown() override {
        Logger::shutdown();
        std::filesystem::remove_all(temp_dir_);
    }

    std::shared_ptr<NiceMock<MockMqttClient>> mock_client_;
    std::filesystem::path temp_dir_;
    SceneRegistry test_registry_;
    TimeChunkBuffer test_buffer_;
    TrackingConfig test_config_;
};

// Test schema gracefully handles missing files and invalid JSON in schema dir
TEST_F(SchemaFileTest, SchemaValidation_HandlesCorruptOrMissingFiles) {
    // Test 1: Schema dir exists but schema files don't
    EXPECT_NO_THROW({
        MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, true,
                               temp_dir_);
        // Handler should still work, just without schema validation
    });

    // Test 2: Create invalid schema files and verify graceful handling
    std::ofstream camera_schema(temp_dir_ / "camera-data.schema.json");
    camera_schema << "{ invalid json }";
    camera_schema.close();

    std::ofstream scene_schema(temp_dir_ / "scene-data.schema.json");
    scene_schema << "{ also invalid }";
    scene_schema.close();

    EXPECT_NO_THROW({
        MessageHandler handler(mock_client_, test_registry_, test_buffer_, test_config_, true,
                               temp_dir_);
        handler.start();

        // Messages should still be processed (no schema to validate against)
        std::string payload = R"({
            "id": "cam1",
            "timestamp": "2026-01-27T12:00:00.000Z",
            "objects": {"person": [{"bounding_box_px": {"x": 0, "y": 0, "width": 10, "height": 20}}]}
        })";
        mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);
    });
}

} // namespace
} // namespace tracker
