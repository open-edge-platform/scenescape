// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "json_utils.hpp"
#include "logger.hpp"
#include "reid_sighting.hpp"

#include <gtest/gtest.h>

namespace tracker {
namespace {

class ReidSightingTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }
};

DetectionBatch make_batch(const std::string& reid = R"({"embedding_vector":[[1,2]]})") {
    DetectionBatch batch;
    batch.camera_id = "cam-1";
    batch.timestamp_iso = "2026-01-27T12:00:00Z";
    Detection detection;
    detection.bounding_box_px = {10, 20, 50, 100};
    detection.reid_json = reid;
    batch.detections.push_back(std::move(detection));
    return batch;
}

TEST_F(ReidSightingTest, ParseSeparatesPayloadConfidenceAndSemanticFields) {
    rapidjson::Document metadata;
    metadata.Parse(
        R"({"reid":{"embedding_vector":[[1,2]],"confidence":0.9},"age":{"label":"adult"}})");
    Detection detection;
    parse_detection_metadata(metadata, detection);
    EXPECT_EQ(detection.metadata_json, R"({"age":{"label":"adult"}})");
    EXPECT_EQ(detection.reid_json, R"({"embedding_vector":[[1,2]],"confidence":0.9})");
    ASSERT_TRUE(detection.reid_confidence);
    EXPECT_DOUBLE_EQ(*detection.reid_confidence, 0.9);
    EXPECT_TRUE(metadata.HasMember("reid"));
}

TEST_F(ReidSightingTest, UnsupportedPayloadsAreNotTagged) {
    for (const auto* json : {R"({"reid":null})", R"({"reid":3})", R"({"reid":true})",
                             R"({"age":{"label":"adult"}})"}) {
        rapidjson::Document metadata;
        metadata.Parse(json);
        auto batch = make_batch();
        batch.detections[0] = Detection{};
        parse_detection_metadata(metadata, batch.detections[0]);
        ReidSightingIndex index;
        index.reset("1");
        const auto context = index.add_batch(batch);
        std::unordered_map<std::string, std::string> attributes;
        context.tag(0, attributes);
        EXPECT_TRUE(attributes.empty());
        EXPECT_TRUE(batch.detections[0].reid_json.empty());
    }
}

TEST_F(ReidSightingTest, ParsingAnotherObservationClearsPreviousReid) {
    Detection detection;
    rapidjson::Document metadata;
    metadata.Parse(R"({"reid":{"embedding_vector":[[1,2]],"confidence":0.9}})");
    parse_detection_metadata(metadata, detection);
    ASSERT_TRUE(detection.reid_confidence);

    metadata.Parse(R"({"age":{"label":"adult"}})");
    parse_detection_metadata(metadata, detection);
    EXPECT_TRUE(detection.reid_json.empty());
    EXPECT_FALSE(detection.reid_confidence);
    EXPECT_EQ(detection.metadata_json, R"({"age":{"label":"adult"}})");
}

TEST_F(ReidSightingTest, OnlyRequestedWinnerIsSerializedAndConsumedOnce) {
    auto first = make_batch();
    auto second = make_batch(R"({"embedding_vector":[[3,4]]})");
    second.camera_id = "cam-2";
    ReidSightingIndex index;
    index.reset("7");
    const auto first_context = index.add_batch(first);
    const auto second_context = index.add_batch(second);
    std::unordered_map<std::string, std::string> winner;
    first_context.tag(0, winner);
    second_context.tag(0, winner);
    // The index holds references, not eagerly serialized sightings.
    second.detections[0].reid_json = R"({"embedding_vector":[[5,6]]})";
    rapidjson::Document sighting;
    ASSERT_FALSE(sighting.Parse(index.take(winner).c_str()).HasParseError());
    EXPECT_STREQ(sighting["camera_id"].GetString(), "cam-2");
    EXPECT_EQ(sighting["reid"]["embedding_vector"][0][0].GetInt(), 5);
    EXPECT_TRUE(index.take(winner).empty());
}

TEST_F(ReidSightingTest, PreviousChunkCannotResolveIntoReusedIndex) {
    auto batch = make_batch();
    ReidSightingIndex index;
    index.reset("1");
    const auto context = index.add_batch(batch);
    std::unordered_map<std::string, std::string> attributes;
    context.tag(0, attributes);
    index.reset("2");
    index.add_batch(batch);
    EXPECT_TRUE(index.take(attributes).empty());
    index.clear();
    EXPECT_TRUE(index.take(attributes).empty());
}

TEST_F(ReidSightingTest, IndicesIncludeSkippedDetectionsAndEarlierBatches) {
    auto first = make_batch();
    first.detections.insert(first.detections.begin(), Detection{});
    auto second = make_batch(R"({"embedding_vector":[[5,6]]})");
    second.camera_id = "cam-2";
    ReidSightingIndex index;
    index.reset("chunk");
    const auto first_context = index.add_batch(first);
    const auto second_context = index.add_batch(second);

    std::unordered_map<std::string, std::string> attributes;
    first_context.tag(0, attributes);
    EXPECT_TRUE(attributes.empty());
    first_context.tag(1, attributes);
    EXPECT_EQ(attributes.at(kReidValueKey), "chunk:1");
    const auto first_sighting = index.take(attributes);
    ASSERT_FALSE(first_sighting.empty());
    rapidjson::Document first_json;
    ASSERT_FALSE(first_json.Parse(first_sighting.c_str()).HasParseError());
    EXPECT_STREQ(first_json["camera_id"].GetString(), "cam-1");

    attributes.clear();
    second_context.tag(0, attributes);
    EXPECT_EQ(attributes.at(kReidValueKey), "chunk:2");
    const auto second_sighting = index.take(attributes);
    ASSERT_FALSE(second_sighting.empty());
    rapidjson::Document second_json;
    ASSERT_FALSE(second_json.Parse(second_sighting.c_str()).HasParseError());
    EXPECT_STREQ(second_json["camera_id"].GetString(), "cam-2");
    EXPECT_EQ(second_json["reid"]["embedding_vector"][0][0].GetInt(), 5);
}

TEST_F(ReidSightingTest, InvalidCurrentChunkTokensAreRejected) {
    auto batch = make_batch();
    ReidSightingIndex index;
    index.reset("1");
    index.add_batch(batch);
    for (const auto* token :
         {"wrong:0", "1:", "1:-1", "1:0junk", "1:4", "1:999999999999999999999999999999999999"}) {
        EXPECT_TRUE(index.take({{kReidValueKey, token}, {kReidProvenanceKey, "1"}}).empty());
    }
    EXPECT_TRUE(index.take({{kReidValueKey, "1:0"}}).empty());
    EXPECT_TRUE(index.take({{kReidProvenanceKey, "1"}}).empty());
}

TEST_F(ReidSightingTest, LegacyEncodingsPreserveStringsAndArrays) {
    for (const auto* payload : {R"({"reid":"AACAPwAAAEA="})", R"({"reid":[[1,2]]})"}) {
        rapidjson::Document metadata;
        metadata.Parse(payload);
        Detection detection;
        parse_detection_metadata(metadata, detection);
        rapidjson::Document normalized;
        ASSERT_FALSE(normalized.Parse(detection.reid_json.c_str()).HasParseError());
        EXPECT_EQ(normalized["embedding_vector"], metadata["reid"]);
        EXPECT_EQ(detection.metadata_json, "{}");
    }
}

TEST(JsonUtilsTest, SerializePreservesEscapingAndEmbeddedNulls) {
    rapidjson::Document value;
    value.Parse(R"({"camera":"cam\"\\\u0000","numbers":[1,2],"empty":{}})");
    const auto json = detail::to_json_string(value);
    rapidjson::Document roundtrip;
    ASSERT_FALSE(roundtrip.Parse(json.data(), json.size()).HasParseError());
    EXPECT_EQ(value, roundtrip);
}

} // namespace
} // namespace tracker
