// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "track_publisher.hpp"

#include "logger.hpp"
#include "utils/mock_mqtt_client.hpp"

#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <rapidjson/document.h>

namespace tracker {
namespace {

using test::MockMqttClient;
using ::testing::_;
using ::testing::Return;

class TrackPublisherTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }

    // Helper to create a sample Track
    Track createSampleTrack(const std::string& id, const std::string& category) {
        Track track;
        track.id = id;
        track.category = category;
        track.translation = {1.0, 2.0, 0.5};
        track.velocity = {0.5, -0.3, 0.0};
        track.size = {0.5, 0.5, 1.8};
        track.rotation = {0.0, 0.0, 0.0, 1.0};
        return track;
    }
};

// =============================================================================
// publish() tests
// =============================================================================

TEST_F(TrackPublisherTest, Publish_CallsMqttWithCorrectTopic) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    EXPECT_CALL(*mock_client, isConnected()).WillOnce(Return(true));
    EXPECT_CALL(*mock_client, publish("scenescape/data/scene/scene-123/person", _)).Times(1);

    std::vector<Track> tracks = {createSampleTrack("track-1", "person")};
    publisher.publish("scene-123", "Test Scene", "person", "2026-01-27T12:00:00.000Z", tracks);
}

TEST_F(TrackPublisherTest, Publish_IncrementsPublishedCount) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    EXPECT_CALL(*mock_client, isConnected()).WillRepeatedly(Return(true));
    EXPECT_CALL(*mock_client, publish(_, _)).Times(3);

    std::vector<Track> tracks = {createSampleTrack("track-1", "person")};

    publisher.publish("scene-1", "Scene", "person", "2026-01-27T12:00:00.000Z", tracks);
    publisher.publish("scene-1", "Scene", "person", "2026-01-27T12:00:01.000Z", tracks);
    publisher.publish("scene-1", "Scene", "person", "2026-01-27T12:00:02.000Z", tracks);

    EXPECT_EQ(publisher.published_count(), 3);
}

TEST_F(TrackPublisherTest, Publish_DoesNothingWhenDisconnected) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    EXPECT_CALL(*mock_client, isConnected()).WillOnce(Return(false));
    EXPECT_CALL(*mock_client, publish(_, _)).Times(0);

    std::vector<Track> tracks = {createSampleTrack("track-1", "person")};
    publisher.publish("scene-123", "Test Scene", "person", "2026-01-27T12:00:00.000Z", tracks);

    EXPECT_EQ(publisher.published_count(), 0);
}

TEST_F(TrackPublisherTest, Publish_DoesNothingWithNullClient) {
    TrackPublisher publisher(nullptr);

    // Should not crash and should not publish
    std::vector<Track> tracks = {createSampleTrack("track-1", "person")};
    publisher.publish("scene-123", "Test Scene", "person", "2026-01-27T12:00:00.000Z", tracks);

    EXPECT_EQ(publisher.published_count(), 0);
}

// =============================================================================
// serialize() tests - via publish() since serialize is private
// =============================================================================

TEST_F(TrackPublisherTest, Serialize_ProducesValidJsonStructure) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    std::string captured_payload;
    EXPECT_CALL(*mock_client, isConnected()).WillOnce(Return(true));
    EXPECT_CALL(*mock_client, publish(_, _))
        .WillOnce([&captured_payload](const std::string&, const std::string& payload) {
            captured_payload = payload;
        });

    std::vector<Track> tracks = {createSampleTrack("track-1", "person")};
    publisher.publish("scene-123", "Test Scene", "person", "2026-01-27T12:00:00.000Z", tracks);

    // Parse and validate JSON structure
    rapidjson::Document doc;
    ASSERT_FALSE(doc.Parse(captured_payload.c_str()).HasParseError());

    EXPECT_TRUE(doc.HasMember("id"));
    EXPECT_STREQ(doc["id"].GetString(), "scene-123");

    EXPECT_TRUE(doc.HasMember("name"));
    EXPECT_STREQ(doc["name"].GetString(), "Test Scene");

    EXPECT_TRUE(doc.HasMember("timestamp"));
    EXPECT_STREQ(doc["timestamp"].GetString(), "2026-01-27T12:00:00.000Z");

    EXPECT_TRUE(doc.HasMember("objects"));
    EXPECT_TRUE(doc["objects"].IsArray());
    EXPECT_EQ(doc["objects"].Size(), 1u);
}

TEST_F(TrackPublisherTest, Serialize_TrackHasCorrectFields) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    std::string captured_payload;
    EXPECT_CALL(*mock_client, isConnected()).WillOnce(Return(true));
    EXPECT_CALL(*mock_client, publish(_, _))
        .WillOnce([&captured_payload](const std::string&, const std::string& payload) {
            captured_payload = payload;
        });

    Track track;
    track.id = "uuid-abc";
    track.category = "vehicle";
    track.translation = {10.5, 20.3, 0.0};
    track.velocity = {1.0, 2.0, 0.0};
    track.size = {4.5, 2.0, 1.5};
    track.rotation = {0.0, 0.0, 0.707, 0.707};

    publisher.publish("scene-1", "Scene", "vehicle", "2026-01-27T12:00:00.000Z", {track});

    rapidjson::Document doc;
    ASSERT_FALSE(doc.Parse(captured_payload.c_str()).HasParseError());

    const auto& obj = doc["objects"][0];
    EXPECT_STREQ(obj["id"].GetString(), "uuid-abc");
    EXPECT_STREQ(obj["category"].GetString(), "vehicle");

    // Translation [x, y, z]
    EXPECT_TRUE(obj["translation"].IsArray());
    EXPECT_EQ(obj["translation"].Size(), 3u);
    EXPECT_DOUBLE_EQ(obj["translation"][0].GetDouble(), 10.5);
    EXPECT_DOUBLE_EQ(obj["translation"][1].GetDouble(), 20.3);
    EXPECT_DOUBLE_EQ(obj["translation"][2].GetDouble(), 0.0);

    // Velocity [vx, vy, vz]
    EXPECT_TRUE(obj["velocity"].IsArray());
    EXPECT_EQ(obj["velocity"].Size(), 3u);
    EXPECT_DOUBLE_EQ(obj["velocity"][0].GetDouble(), 1.0);
    EXPECT_DOUBLE_EQ(obj["velocity"][1].GetDouble(), 2.0);

    // Size [length, width, height]
    EXPECT_TRUE(obj["size"].IsArray());
    EXPECT_EQ(obj["size"].Size(), 3u);
    EXPECT_DOUBLE_EQ(obj["size"][0].GetDouble(), 4.5);
    EXPECT_DOUBLE_EQ(obj["size"][1].GetDouble(), 2.0);
    EXPECT_DOUBLE_EQ(obj["size"][2].GetDouble(), 1.5);

    // Rotation quaternion [x, y, z, w]
    EXPECT_TRUE(obj["rotation"].IsArray());
    EXPECT_EQ(obj["rotation"].Size(), 4u);
    EXPECT_DOUBLE_EQ(obj["rotation"][2].GetDouble(), 0.707);
    EXPECT_DOUBLE_EQ(obj["rotation"][3].GetDouble(), 0.707);
}

TEST_F(TrackPublisherTest, Serialize_HandlesEmptyTracks) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    std::string captured_payload;
    EXPECT_CALL(*mock_client, isConnected()).WillOnce(Return(true));
    EXPECT_CALL(*mock_client, publish(_, _))
        .WillOnce([&captured_payload](const std::string&, const std::string& payload) {
            captured_payload = payload;
        });

    std::vector<Track> empty_tracks;
    publisher.publish("scene-1", "Scene", "person", "2026-01-27T12:00:00.000Z", empty_tracks);

    rapidjson::Document doc;
    ASSERT_FALSE(doc.Parse(captured_payload.c_str()).HasParseError());
    EXPECT_TRUE(doc["objects"].IsArray());
    EXPECT_EQ(doc["objects"].Size(), 0u);
}

TEST_F(TrackPublisherTest, Serialize_HandlesMultipleTracks) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    std::string captured_payload;
    EXPECT_CALL(*mock_client, isConnected()).WillOnce(Return(true));
    EXPECT_CALL(*mock_client, publish(_, _))
        .WillOnce([&captured_payload](const std::string&, const std::string& payload) {
            captured_payload = payload;
        });

    std::vector<Track> tracks = {
        createSampleTrack("track-1", "person"),
        createSampleTrack("track-2", "person"),
        createSampleTrack("track-3", "person"),
    };
    publisher.publish("scene-1", "Scene", "person", "2026-01-27T12:00:00.000Z", tracks);

    rapidjson::Document doc;
    ASSERT_FALSE(doc.Parse(captured_payload.c_str()).HasParseError());
    EXPECT_EQ(doc["objects"].Size(), 3u);
    EXPECT_STREQ(doc["objects"][0]["id"].GetString(), "track-1");
    EXPECT_STREQ(doc["objects"][1]["id"].GetString(), "track-2");
    EXPECT_STREQ(doc["objects"][2]["id"].GetString(), "track-3");
}

// =============================================================================
// build_topic() tests - via topic verification in publish
// =============================================================================

TEST_F(TrackPublisherTest, BuildTopic_FormatsCorrectly) {
    auto mock_client = std::make_shared<MockMqttClient>();
    TrackPublisher publisher(mock_client);

    EXPECT_CALL(*mock_client, isConnected()).WillRepeatedly(Return(true));

    // Test different scene/category combinations
    EXPECT_CALL(*mock_client, publish("scenescape/data/scene/abc-123/person", _)).Times(1);
    EXPECT_CALL(*mock_client, publish("scenescape/data/scene/xyz-789/vehicle", _)).Times(1);

    std::vector<Track> tracks = {createSampleTrack("t1", "person")};
    publisher.publish("abc-123", "Scene A", "person", "2026-01-27T12:00:00.000Z", tracks);

    tracks = {createSampleTrack("t2", "vehicle")};
    publisher.publish("xyz-789", "Scene B", "vehicle", "2026-01-27T12:00:00.000Z", tracks);
}

} // namespace
} // namespace tracker
