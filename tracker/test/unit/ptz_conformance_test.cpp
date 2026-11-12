// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Replays tests/data/ptz/dwell_conformance.json, unmodified, through the Tracker's public
// path (raw payload -> parser -> registry -> dwell). The Controller replays the same file
// (tests/sscape_tests/scenescape/test_controller_ptz_conformance.py), so both consumers
// produce identical decisions for every shared vector.

#include "ptz_registry.hpp"
#include "ptz_test_utils.hpp"

#include <gtest/gtest.h>

#include <fstream>
#include <set>
#include <sstream>

#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker::ptz {
namespace {

constexpr const char* kSceneFramePrefix = "scene:";

const rapidjson::Document& fixture() {
    static const rapidjson::Document doc = [] {
        std::ifstream ifs(TRACKER_PTZ_CONFORMANCE_FILE);
        std::stringstream content;
        content << ifs.rdbuf();
        rapidjson::Document parsed;
        parsed.Parse(content.str().c_str());
        return parsed;
    }();
    return doc;
}

std::string serialize(const rapidjson::Value& value) {
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    value.Accept(writer);
    return buffer.GetString();
}

int64_t ns(const rapidjson::Value& value) {
    auto parsed = parseIsoTimestampNs(value.GetString());
    EXPECT_TRUE(parsed.has_value()) << value.GetString();
    return parsed.value_or(0);
}

PtzConfig consumerConfig(const rapidjson::Value& config) {
    PtzConfig ptz;
    ptz.max_pose_age_s = config["max_pose_age_s"].GetDouble();
    ptz.max_clock_offset_s = config["max_clock_offset_s"].GetDouble();
    ptz.max_detection_pipeline_latency_s = config["max_detection_pipeline_latency_s"].GetDouble();
    ptz.max_detection_timestamp_uncertainty_s =
        config["max_detection_timestamp_uncertainty_s"].GetDouble();
    return ptz;
}

std::unique_ptr<PtzPoseRegistry> buildRegistry(const rapidjson::Value& vector) {
    const auto& consumer = vector["consumer"];
    const std::string frame_id = consumer["expected_frame_id"].GetString();
    EXPECT_TRUE(frame_id.starts_with(kSceneFramePrefix));
    const std::string source_id = consumer["source_id"].GetString();
    std::optional<std::string> calibration;
    if (consumer["expected_calibration_version"].IsString()) {
        calibration = consumer["expected_calibration_version"].GetString();
    }
    const std::vector<Scene> scenes = {
        test::scene({test::camera(source_id, true, calibration)},
                    frame_id.substr(std::strlen(kSceneFramePrefix)))};
    const Assignments assignments = {{source_id, consumer["resolver_id"].GetString()}};
    return std::make_unique<PtzPoseRegistry>(
        scenes, assignments, dwellConfigFrom(consumerConfig(vector["config"])),
        PtzMessageParser(TRACKER_SCHEMA_DIR), [] { return PtzClockReading{0, true}; });
}

/// Returns the number of observations checked.
int replay(const rapidjson::Value& vector) {
    auto registry = buildRegistry(vector);
    const std::string name = vector["name"].GetString();
    const std::string source_id = vector["consumer"]["source_id"].GetString();
    const std::string pose_topic = test::poseTopic(source_id);
    int checked = 0;
    int index = 0;
    for (const auto& event : vector["events"].GetArray()) {
        const std::string where = name + " event #" + std::to_string(index++);
        const std::string type = event["type"].GetString();
        if (type == "status") {
            const auto& payload = event["payload"];
            EXPECT_EQ(
                registry->onStatusMessage(test::statusTopic(payload["resolver_id"].GetString()),
                                          serialize(payload)),
                std::nullopt)
                << where;
        } else if (type == "pose") {
            EXPECT_EQ(registry->onPoseMessage(pose_topic, serialize(event["payload"])),
                      std::nullopt)
                << where;
        } else {
            const auto admission = registry->admitAt(source_id, ns(event["timestamp"]),
                                                     {ns(event["local_now"]), true});
            const auto& expected = event["expected"];
            EXPECT_EQ(admission.admitted, expected["admitted"].GetBool()) << where;
            EXPECT_EQ(admission.pose != nullptr && admission.admitted,
                      expected["admitted"].GetBool())
                << where;
            if (!expected["admitted"].GetBool()) {
                EXPECT_STREQ(toString(admission.invalid_reason),
                             expected["invalid_reason"].GetString())
                    << where;
                const auto& detail = expected["reason_detail"];
                EXPECT_STREQ(toString(admission.reason_detail),
                             detail.IsString() ? detail.GetString() : "")
                    << where;
            }
            ++checked;
        }
    }
    return checked;
}

TEST(PtzConformanceTest, FixtureIsVersionOneAndNonEmpty) {
    const auto& doc = fixture();
    ASSERT_TRUE(doc.IsObject()) << "cannot read " << TRACKER_PTZ_CONFORMANCE_FILE;
    EXPECT_EQ(doc["fixture_version"].GetInt(), 1);
    EXPECT_GT(doc["vectors"].Size(), 0u);
}

TEST(PtzConformanceTest, TrackerMatchesEveryVector) {
    const auto& doc = fixture();
    ASSERT_TRUE(doc.IsObject());
    for (const auto& vector : doc["vectors"].GetArray()) {
        SCOPED_TRACE(vector["name"].GetString());
        EXPECT_GT(replay(vector), 0);
    }
}

TEST(PtzConformanceTest, FixtureCoversEveryReasonDetail) {
    const auto& doc = fixture();
    ASSERT_TRUE(doc.IsObject());
    std::set<std::string> seen;
    for (const auto& vector : doc["vectors"].GetArray()) {
        for (const auto& event : vector["events"].GetArray()) {
            if (std::string(event["type"].GetString()) == "observation" &&
                !event["expected"]["admitted"].GetBool()) {
                seen.insert(event["expected"]["reason_detail"].GetString());
            }
        }
    }
    std::set<std::string> all;
    for (size_t i = 1; i < kReasonDetailCount; ++i) {
        all.insert(toString(static_cast<ReasonDetail>(i)));
    }
    EXPECT_EQ(seen, all);
}

} // namespace
} // namespace tracker::ptz
