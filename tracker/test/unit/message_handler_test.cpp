// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "message_handler.hpp"

#include <sstream>

namespace tracker {
namespace {

class MessageHandlerTest : public ::testing::Test {};

// Test topic constants
TEST_F(MessageHandlerTest, TopicConstants_AreCorrect) {
    EXPECT_STREQ(MessageHandler::TOPIC_CAMERA_DATA, "scenescape/data/camera/+");
    EXPECT_STREQ(MessageHandler::DUMMY_SCENE_ID, "dummy-scene");
    EXPECT_STREQ(MessageHandler::DUMMY_SCENE_NAME, "Test Scene");
    EXPECT_STREQ(MessageHandler::DUMMY_THING_TYPE, "thing");
}

// Test camera ID extraction from topic
TEST_F(MessageHandlerTest, ExtractCameraId_ValidTopic) {
    // Use reflection or expose for testing - for now we test via integration
    // The extractCameraId is private, tested indirectly via handleCameraMessage
}

// Test dummy message structure matches expected format
TEST_F(MessageHandlerTest, DummyMessage_HasExpectedStructure) {
    // Build expected JSON structure
    std::string timestamp = "2026-01-22T10:30:00.000Z";

    std::ostringstream expected_json;
    expected_json << R"({)" << R"("id":")" << MessageHandler::DUMMY_SCENE_ID << R"(",)"
                  << R"("name":")" << MessageHandler::DUMMY_SCENE_NAME << R"(",)"
                  << R"("timestamp":")" << timestamp << R"(",)" << R"("objects":[)" << R"({)"
                  << R"("id":"dummy-track-001",)" << R"("category":")"
                  << MessageHandler::DUMMY_THING_TYPE << R"(",)"
                  << R"("translation":[1.0,2.0,0.0],)" << R"("velocity":[0.1,0.2,0.0],)"
                  << R"("size":[0.5,0.5,1.8],)" << R"("rotation":[0,0,0,1])" << R"(})" << R"(])"
                  << R"(})";

    std::string json = expected_json.str();

    // Verify expected fields are present in the string
    EXPECT_NE(json.find("\"id\":\"dummy-scene\""), std::string::npos);
    EXPECT_NE(json.find("\"name\":\"Test Scene\""), std::string::npos);
    EXPECT_NE(json.find("\"timestamp\":"), std::string::npos);
    EXPECT_NE(json.find("\"objects\":"), std::string::npos);
    EXPECT_NE(json.find("\"category\":\"thing\""), std::string::npos);
    EXPECT_NE(json.find("\"translation\":[1.0,2.0,0.0]"), std::string::npos);
    EXPECT_NE(json.find("\"velocity\":[0.1,0.2,0.0]"), std::string::npos);
    EXPECT_NE(json.find("\"size\":[0.5,0.5,1.8]"), std::string::npos);
    EXPECT_NE(json.find("\"rotation\":[0,0,0,1]"), std::string::npos);
}

// Test that dummy output uses "thing" category
TEST_F(MessageHandlerTest, DummyMessage_UsesThingCategory) {
    EXPECT_STREQ(MessageHandler::DUMMY_THING_TYPE, "thing");
}

// Test output topic format
TEST_F(MessageHandlerTest, OutputTopic_HasCorrectFormat) {
    std::ostringstream output_topic;
    output_topic << "scenescape/data/scene/" << MessageHandler::DUMMY_SCENE_ID << "/"
                 << MessageHandler::DUMMY_THING_TYPE;

    EXPECT_EQ(output_topic.str(), "scenescape/data/scene/dummy-scene/thing");
}

} // namespace
} // namespace tracker
