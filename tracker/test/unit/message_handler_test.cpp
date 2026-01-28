// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "logger.hpp"
#include "message_handler.hpp"
#include "mqtt_client.hpp"

#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace tracker {
namespace {

using ::testing::_;
using ::testing::Invoke;
using ::testing::NiceMock;
using ::testing::Return;
using ::testing::StrictMock;

/**
 * @brief Mock MQTT client for unit testing MessageHandler.
 */
class MockMqttClient : public IMqttClient {
public:
    MOCK_METHOD(void, connect, (), (override));
    MOCK_METHOD(void, disconnect, (std::chrono::milliseconds drain_timeout), (override));
    MOCK_METHOD(void, subscribe, (const std::string& topic), (override));
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
    }

    void TearDown() override { Logger::shutdown(); }

    std::shared_ptr<NiceMock<MockMqttClient>> mock_client_;
};

// Test topic constants
TEST_F(MessageHandlerTest, TopicConstants_AreCorrect) {
    EXPECT_STREQ(MessageHandler::TOPIC_CAMERA_DATA, "scenescape/data/camera/+");
    EXPECT_STREQ(MessageHandler::DUMMY_SCENE_ID, "dummy-scene");
    EXPECT_STREQ(MessageHandler::DUMMY_SCENE_NAME, "Test Scene");
    EXPECT_STREQ(MessageHandler::DUMMY_THING_TYPE, "thing");
}

// Test output topic format
TEST_F(MessageHandlerTest, OutputTopic_HasCorrectFormat) {
    std::ostringstream output_topic;
    output_topic << "scenescape/data/scene/" << MessageHandler::DUMMY_SCENE_ID << "/"
                 << MessageHandler::DUMMY_THING_TYPE;

    EXPECT_EQ(output_topic.str(), "scenescape/data/scene/dummy-scene/thing");
}

// Test that handler subscribes to camera topic on start
TEST_F(MessageHandlerTest, Start_SubscribesToCameraTopic) {
    EXPECT_CALL(*mock_client_, subscribe(MessageHandler::TOPIC_CAMERA_DATA)).Times(1);

    // Disable schema validation since we don't have schemas in test env
    MessageHandler handler(mock_client_, false);
    handler.start();
}

// Test that handler sets message callback on start
TEST_F(MessageHandlerTest, Start_SetsMessageCallback) {
    EXPECT_CALL(*mock_client_, setMessageCallback(_)).Times(1);

    MessageHandler handler(mock_client_, false);
    handler.start();
}

// Test processing valid camera message increments received count
TEST_F(MessageHandlerTest, HandleMessage_IncrementsReceivedCount) {
    MessageHandler handler(mock_client_, false);
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

// Test processing valid message triggers publish
TEST_F(MessageHandlerTest, HandleMessage_PublishesOutput) {
    std::vector<std::pair<std::string, std::string>> published_messages;

    ON_CALL(*mock_client_, publish(_, _))
        .WillByDefault(Invoke([&](const std::string& topic, const std::string& payload) {
            published_messages.emplace_back(topic, payload);
        }));

    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    ASSERT_EQ(published_messages.size(), 1);
    EXPECT_EQ(published_messages[0].first, "scenescape/data/scene/dummy-scene/thing");
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test published output contains required fields
TEST_F(MessageHandlerTest, PublishedOutput_ContainsRequiredFields) {
    std::string published_payload;

    ON_CALL(*mock_client_, publish(_, _))
        .WillByDefault(Invoke([&](const std::string& /*topic*/, const std::string& payload) {
            published_payload = payload;
        }));

    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string input_payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [{"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50, "height": 100}}]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", input_payload);

    // Parse the published output
    rapidjson::Document doc;
    doc.Parse(published_payload.c_str());
    ASSERT_FALSE(doc.HasParseError()) << "Published JSON should be valid";

    // Check required fields
    EXPECT_TRUE(doc.HasMember("id"));
    EXPECT_TRUE(doc.HasMember("name"));
    EXPECT_TRUE(doc.HasMember("timestamp"));
    EXPECT_TRUE(doc.HasMember("objects"));

    EXPECT_STREQ(doc["id"].GetString(), MessageHandler::DUMMY_SCENE_ID);
    EXPECT_STREQ(doc["name"].GetString(), MessageHandler::DUMMY_SCENE_NAME);
    EXPECT_TRUE(doc["objects"].IsArray());
}

// Test that invalid JSON is rejected
TEST_F(MessageHandlerTest, HandleMessage_RejectsInvalidJson) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string invalid_json = "{ this is not valid json }";
    mock_client_->simulateMessage("scenescape/data/camera/cam1", invalid_json);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getPublishedCount(), 0);
}

// Test that message missing required fields is rejected
TEST_F(MessageHandlerTest, HandleMessage_RejectsMissingFields) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    // Missing 'objects' field
    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z"
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getPublishedCount(), 0);
}

// Test that empty objects map still produces output
TEST_F(MessageHandlerTest, HandleMessage_AcceptsEmptyObjects) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test multiple objects categories are parsed correctly
TEST_F(MessageHandlerTest, HandleMessage_ParsesMultipleCategories) {
    MessageHandler handler(mock_client_, false);
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
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test detection without id is valid (id is optional)
TEST_F(MessageHandlerTest, HandleMessage_AcceptsDetectionWithoutId) {
    MessageHandler handler(mock_client_, false);
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
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test bounding box validation - missing field skips the detection but doesn't reject message
TEST_F(MessageHandlerTest, HandleMessage_SkipsInvalidBoundingBox) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    // Missing 'height' in bounding_box_px - detection should be skipped
    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [
                {"id": 1, "bounding_box_px": {"x": 10, "y": 20, "width": 50}}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    // Message is received and processed (with 0 valid detections)
    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);  // Message not rejected
    EXPECT_EQ(handler.getPublishedCount(), 1); // Still publishes output
}

// Test output timestamp matches input timestamp
TEST_F(MessageHandlerTest, PublishedOutput_PreservesTimestamp) {
    std::string published_payload;

    ON_CALL(*mock_client_, publish(_, _))
        .WillByDefault(Invoke([&](const std::string& /*topic*/, const std::string& payload) {
            published_payload = payload;
        }));

    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string expected_timestamp = "2026-01-27T15:45:30.123Z";
    std::string input_payload = R"({
        "id": "cam1",
        "timestamp": ")" + expected_timestamp +
                                R"(",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", input_payload);

    rapidjson::Document doc;
    doc.Parse(published_payload.c_str());
    ASSERT_FALSE(doc.HasParseError());
    ASSERT_TRUE(doc.HasMember("timestamp"));
    EXPECT_STREQ(doc["timestamp"].GetString(), expected_timestamp.c_str());
}

// Test that stop() can be called safely
TEST_F(MessageHandlerTest, Stop_CanBeCalled) {
    MessageHandler handler(mock_client_, false);
    handler.start();
    handler.stop(); // Should not throw
    SUCCEED();
}

// Test handler with schema validation disabled accepts all valid JSON
TEST_F(MessageHandlerTest, SchemaValidationDisabled_AcceptsValidJson) {
    MessageHandler handler(mock_client_, false); // schema_validation = false
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getRejectedCount(), 0);
}

// Test that dummy output contains objects array with expected structure
TEST_F(MessageHandlerTest, DummyOutput_HasExpectedObjectStructure) {
    std::string published_payload;

    ON_CALL(*mock_client_, publish(_, _))
        .WillByDefault(Invoke([&](const std::string& /*topic*/, const std::string& payload) {
            published_payload = payload;
        }));

    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string input_payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {"person": [{"id": 1, "bounding_box_px": {"x": 0, "y": 0, "width": 10, "height": 20}}]}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", input_payload);

    rapidjson::Document doc;
    doc.Parse(published_payload.c_str());
    ASSERT_FALSE(doc.HasParseError());
    ASSERT_TRUE(doc.HasMember("objects"));
    ASSERT_TRUE(doc["objects"].IsArray());
    ASSERT_GT(doc["objects"].Size(), 0u);

    const auto& obj = doc["objects"][0];
    EXPECT_TRUE(obj.HasMember("id"));
    EXPECT_TRUE(obj.HasMember("category"));
    EXPECT_TRUE(obj.HasMember("translation"));
    EXPECT_TRUE(obj.HasMember("velocity"));
    EXPECT_TRUE(obj.HasMember("size"));
    EXPECT_TRUE(obj.HasMember("rotation"));
    EXPECT_STREQ(obj["category"].GetString(), MessageHandler::DUMMY_THING_TYPE);
}

//
// Edge case tests (coverage for missing lines)
//

// Test empty camera ID is rejected (covers lines 105-107)
TEST_F(MessageHandlerTest, HandleMessage_RejectsEmptyCameraId) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    // Topic with trailing slash but no camera ID
    mock_client_->simulateMessage("scenescape/data/camera/", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getPublishedCount(), 0);
}

// Test malformed topic prefix is rejected
TEST_F(MessageHandlerTest, HandleMessage_RejectsWrongTopicPrefix) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    // Completely different topic
    mock_client_->simulateMessage("other/topic/cam1", payload);

    // Should be rejected due to not matching camera topic pattern
    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
}

// Test detection missing bounding_box_px entirely (covers lines 181-182)
TEST_F(MessageHandlerTest, HandleMessage_SkipsDetectionWithoutBoundingBox) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [
                {"id": 1}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);  // Message not rejected
    EXPECT_EQ(handler.getPublishedCount(), 1); // Still publishes (with 0 detections)
}

// Test detection with non-object bounding_box_px (covers lines 181-182)
TEST_F(MessageHandlerTest, HandleMessage_SkipsDetectionWithNonObjectBoundingBox) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [
                {"id": 1, "bounding_box_px": "not_an_object"}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test detection with bounding_box_px as array instead of object
TEST_F(MessageHandlerTest, HandleMessage_SkipsDetectionWithArrayBoundingBox) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": [
                {"id": 1, "bounding_box_px": [10, 20, 50, 100]}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

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

// Test constructor with schema validation enabled loads schemas
TEST_F(MessageHandlerTest, SchemaValidation_LoadsSchemas) {
    auto schema_dir = get_schema_dir();

    // Should not throw when schemas exist
    EXPECT_NO_THROW({ MessageHandler handler(mock_client_, true, schema_dir); });
}

// Test valid message passes schema validation
TEST_F(MessageHandlerTest, SchemaValidation_AcceptsValidMessage) {
    auto schema_dir = get_schema_dir();
    MessageHandler handler(mock_client_, true, schema_dir);
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
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test invalid message is rejected by schema validation
TEST_F(MessageHandlerTest, SchemaValidation_RejectsInvalidMessage) {
    auto schema_dir = get_schema_dir();
    MessageHandler handler(mock_client_, true, schema_dir);
    handler.start();

    // Missing required "timestamp" field
    std::string payload = R"({
        "id": "cam1",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getPublishedCount(), 0);
}

// Test schema validation with complete message
TEST_F(MessageHandlerTest, SchemaValidation_WithCompleteMessage) {
    auto schema_dir = get_schema_dir();
    MessageHandler handler(mock_client_, true, schema_dir);
    handler.start();

    // Complete message with all expected fields
    std::string payload = R"({
        "id": "camera-001",
        "timestamp": "2026-01-28T10:30:00.000Z",
        "objects": {
            "person": [
                {"id": 1, "bounding_box_px": {"x": 100, "y": 200, "width": 80, "height": 160}},
                {"id": 2, "bounding_box_px": {"x": 300, "y": 150, "width": 70, "height": 140}}
            ],
            "vehicle": [
                {"id": 3, "bounding_box_px": {"x": 500, "y": 400, "width": 200, "height": 100}}
            ]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/camera-001", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test with invalid schema directory logs warning but continues
TEST_F(MessageHandlerTest, SchemaValidation_InvalidDirFallsBack) {
    // Non-existent schema directory
    std::filesystem::path bad_dir = "/nonexistent/schema/dir";

    // Should not throw, just log warning
    EXPECT_NO_THROW({
        MessageHandler handler(mock_client_, true, bad_dir);
        handler.start();

        // Without schemas loaded, messages should still be processed
        std::string payload = R"({
            "id": "cam1",
            "timestamp": "2026-01-27T12:00:00.000Z",
            "objects": {}
        })";

        mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);
    });
}

// Test category with non-array value is skipped (covers lines 197-199)
TEST_F(MessageHandlerTest, HandleMessage_SkipsCategoryWithNonArrayValue) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    // Category "person" has a string instead of array
    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": "not_an_array"
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);  // Message not rejected, just category skipped
    EXPECT_EQ(handler.getPublishedCount(), 1); // Still publishes output
}

// Test detection that is not an object is skipped
TEST_F(MessageHandlerTest, HandleMessage_SkipsNonObjectDetection) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    // Detection is a string instead of object
    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {
            "person": ["not_an_object", 123, null]
        }
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 0);
    EXPECT_EQ(handler.getPublishedCount(), 1);
}

// Test topic that is too short is rejected
TEST_F(MessageHandlerTest, HandleMessage_RejectsTooShortTopic) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    // Topic shorter than expected prefix
    mock_client_->simulateMessage("scenescape/data", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
}

// Test topic with correct length but wrong prefix is rejected (covers line 148)
TEST_F(MessageHandlerTest, HandleMessage_RejectsWrongPrefix) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    // Same length as "scenescape/data/camera/cam1" but different prefix
    mock_client_->simulateMessage("wrongprefix/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
}

// Test missing 'id' field in camera message (covers lines 175-176)
TEST_F(MessageHandlerTest, HandleMessage_RejectsMissingId) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getPublishedCount(), 0);
}

// Test invalid 'id' field type (covers lines 175-176)
TEST_F(MessageHandlerTest, HandleMessage_RejectsNonStringId) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": 123,
        "timestamp": "2026-01-27T12:00:00.000Z",
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getPublishedCount(), 0);
}

// Test invalid 'timestamp' field type (covers lines 181-182)
TEST_F(MessageHandlerTest, HandleMessage_RejectsNonStringTimestamp) {
    MessageHandler handler(mock_client_, false);
    handler.start();

    std::string payload = R"({
        "id": "cam1",
        "timestamp": 1234567890,
        "objects": {}
    })";

    mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);

    EXPECT_EQ(handler.getReceivedCount(), 1);
    EXPECT_EQ(handler.getRejectedCount(), 1);
    EXPECT_EQ(handler.getPublishedCount(), 0);
}

//
// Schema file loading edge cases (covers lines 73, 75)
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
    }

    void TearDown() override {
        Logger::shutdown();
        std::filesystem::remove_all(temp_dir_);
    }

    std::shared_ptr<NiceMock<MockMqttClient>> mock_client_;
    std::filesystem::path temp_dir_;
};

// Test schema file that can't be opened (covers line 73 - file not found)
TEST_F(SchemaFileTest, SchemaValidation_FileNotFound) {
    // Schema dir exists but schema files don't
    EXPECT_NO_THROW({
        MessageHandler handler(mock_client_, true, temp_dir_);
        // Handler should still work, just without schema validation
    });
}

// Test schema file with invalid JSON (covers line 75 - parse error)
TEST_F(SchemaFileTest, SchemaValidation_InvalidSchemaJson) {
    // Create invalid schema files
    std::ofstream camera_schema(temp_dir_ / "camera-data.schema.json");
    camera_schema << "{ invalid json }";
    camera_schema.close();

    std::ofstream scene_schema(temp_dir_ / "scene-data.schema.json");
    scene_schema << "{ also invalid }";
    scene_schema.close();

    EXPECT_NO_THROW({
        MessageHandler handler(mock_client_, true, temp_dir_);
        handler.start();

        // Messages should still be processed (no schema to validate against)
        std::string payload = R"({
            "id": "cam1",
            "timestamp": "2026-01-27T12:00:00.000Z",
            "objects": {}
        })";
        mock_client_->simulateMessage("scenescape/data/camera/cam1", payload);
    });
}

} // namespace
} // namespace tracker
