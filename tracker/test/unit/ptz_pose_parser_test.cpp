// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_pose_parser.hpp"
#include "ptz_test_utils.hpp"

#include <gtest/gtest.h>

#include <fstream>
#include <limits>
#include <sstream>

#include <rapidjson/document.h>

namespace tracker::ptz {
namespace {

using test::PoseJson;

class PtzPoseParserTest : public ::testing::Test {
protected:
    PtzMessageParser parser_{TRACKER_SCHEMA_DIR};
};

TEST_F(PtzPoseParserTest, ParsesValidStationaryPoseAndPrecomputesView) {
    PoseJson json;
    json.matrix = test::yawMatrix(90.0, {1.0, 2.0, 4.0});
    auto result = parser_.parsePose(json.json());
    ASSERT_FALSE(result.stage.has_value());
    ASSERT_TRUE(result.pose);
    const auto& pose = *result.pose;
    EXPECT_EQ(pose.source_id, test::kSourceId);
    EXPECT_EQ(pose.timestamp_ns, test::kBaseNs);
    EXPECT_EQ(pose.valid_until_ns, test::kBaseNs + test::ms(1000));
    EXPECT_EQ(pose.timestamp_uncertainty_ns, 10'000'000);
    EXPECT_EQ(pose.motion_state, MotionState::Stationary);
    EXPECT_EQ(pose.frame_id, std::string("scene:scene-1"));
    ASSERT_TRUE(pose.view.has_value());
    EXPECT_DOUBLE_EQ(pose.view->origin.x, 1.0);
    EXPECT_DOUBLE_EQ(pose.view->origin.z, 4.0);
    EXPECT_NEAR(pose.view->rotation(1, 0), 1.0, 1e-12);
    EXPECT_DOUBLE_EQ(pose.view->horizon_distance, PoseView::horizonDistanceFor(4.0));
}

TEST_F(PtzPoseParserTest, ParsesInvalidPoseReasons) {
    PoseJson json;
    json.valid = false;
    json.motion_state = "slewing";
    json.invalid_reason = "invalid_pose";
    json.reason_detail = "moving";
    auto result = parser_.parsePose(json.json());
    ASSERT_TRUE(result.pose);
    EXPECT_FALSE(result.pose->valid);
    EXPECT_FALSE(result.pose->view.has_value());
    EXPECT_EQ(result.pose->invalid_reason, InvalidReason::InvalidPose);
    EXPECT_EQ(result.pose->reason_detail, ReasonDetail::Moving);
    EXPECT_FALSE(result.pose->frame_id.has_value());
}

TEST_F(PtzPoseParserTest, RejectsOversizedMalformedAndSchemaInvalidPayloads) {
    EXPECT_EQ(parser_.parsePose(std::string(kMaxPoseContextBytes + 1, ' ')).stage,
              PoseRejectStage::Size);
    EXPECT_EQ(parser_.parsePose("{not json").stage, PoseRejectStage::Json);
    EXPECT_EQ(parser_.parsePose(R"({"source_id":"x"})").stage, PoseRejectStage::Schema);

    PoseJson extra;
    auto with_extra = extra.json();
    with_extra.insert(1, R"("unexpected":1,)");
    EXPECT_EQ(parser_.parsePose(with_extra).stage, PoseRejectStage::Schema);

    PoseJson bad_motion;
    bad_motion.motion_state = "spinning";
    EXPECT_EQ(parser_.parsePose(bad_motion.json()).stage, PoseRejectStage::Schema);

    // valid:true must not carry invalid_reason (oneOf)
    PoseJson both;
    auto mixed = both.json();
    mixed.insert(1, R"("invalid_reason":"invalid_pose",)");
    EXPECT_EQ(parser_.parsePose(mixed).stage, PoseRejectStage::Schema);
}

TEST_F(PtzPoseParserTest, RejectsUnparseableTimestampsAtSchemaStage) {
    PoseJson json;
    auto text = json.json();
    const auto at = text.find("\"timestamp\":\"") + 13;
    text.replace(at, 4, "XXXX");
    EXPECT_EQ(parser_.parsePose(text).stage, PoseRejectStage::Schema);
}

TEST_F(PtzPoseParserTest, RejectsNonRigidMatrices) {
    PoseJson scaled;
    scaled.matrix = test::yawMatrix(0.0);
    scaled.matrix[0] = 2.0;
    EXPECT_EQ(parser_.parsePose(scaled.json()).stage, PoseRejectStage::Guard);

    PoseJson reflected;
    reflected.matrix = test::yawMatrix(0.0);
    reflected.matrix[10] = -1.0; // det -1
    EXPECT_EQ(parser_.parsePose(reflected.json()).stage, PoseRejectStage::Guard);

    PoseJson last_row;
    last_row.matrix = test::yawMatrix(0.0);
    last_row.matrix[12] = 0.5;
    EXPECT_EQ(parser_.parsePose(last_row.json()).stage, PoseRejectStage::Guard);

    PoseJson within_tolerance;
    within_tolerance.matrix = test::yawMatrix(30.0);
    within_tolerance.matrix[15] = 1.0 + 5e-7;
    EXPECT_FALSE(parser_.parsePose(within_tolerance.json()).stage.has_value());
}

TEST_F(PtzPoseParserTest, RejectsNonFiniteNumbersAsJson) {
    PoseJson json;
    auto text = json.json();
    const auto at = text.find("\"sample_age_s\":") + 15;
    text.replace(at, 3, "1e999");
    EXPECT_EQ(parser_.parsePose(text).stage, PoseRejectStage::Json);
    auto nan_text = json.json();
    nan_text.replace(nan_text.find("\"sample_age_s\":") + 15, 3, "NaN");
    EXPECT_EQ(parser_.parsePose(nan_text).stage, PoseRejectStage::Json);
}

TEST_F(PtzPoseParserTest, RejectsOversizedMatrixArrays) {
    PoseJson json;
    auto text = json.json();
    const auto at = text.find("[[") + 1;
    text.insert(at, "[0,0,0,0],");
    EXPECT_EQ(parser_.parsePose(text).stage, PoseRejectStage::Schema);
}

TEST_F(PtzPoseParserTest, ParsesStatusAndRejectsBadStatus) {
    auto online = parser_.parseStatus(test::statusJson("positioning", "online", test::kBaseNs));
    ASSERT_TRUE(online.status.has_value());
    EXPECT_TRUE(online.status->online);
    EXPECT_EQ(online.status->session_ns, test::kBaseNs);
    EXPECT_EQ(online.status->resolver_id, "positioning");

    auto offline = parser_.parseStatus(test::statusJson("positioning", "offline", test::kBaseNs));
    ASSERT_TRUE(offline.status.has_value());
    EXPECT_FALSE(offline.status->online);

    EXPECT_EQ(parser_.parseStatus(std::string(kMaxStatusBytes + 1, ' ')).stage,
              PoseRejectStage::Size);
    EXPECT_EQ(parser_.parseStatus("[").stage, PoseRejectStage::Json);
    EXPECT_EQ(parser_.parseStatus(test::statusJson("p", "sleeping", test::kBaseNs)).stage,
              PoseRejectStage::Schema);
    EXPECT_EQ(parser_.parseStatus(R"({"resolver_id":"p","status":"online","timestamp":"x"})").stage,
              PoseRejectStage::Schema);
}

TEST(PtzPoseParserSetupTest, MissingSchemaThrowsAndStagesHaveLabels) {
    EXPECT_THROW(PtzMessageParser("/nonexistent"), std::runtime_error);
    EXPECT_STREQ(toString(PoseRejectStage::Size), "size");
    EXPECT_STREQ(toString(PoseRejectStage::Json), "json");
    EXPECT_STREQ(toString(PoseRejectStage::Schema), "schema");
    EXPECT_STREQ(toString(PoseRejectStage::Guard), "guard");
    EXPECT_STREQ(toString(PoseRejectStage::Topic), "topic");
    EXPECT_STREQ(toString(PoseRejectStage::Unmanaged), "unmanaged");
}

// The Tracker validates with verbatim copies of the Controller's PoseContext and status
// definitions; this guards them against drift.

rapidjson::Document readJson(const std::string& path) {
    std::ifstream ifs(path);
    std::stringstream content;
    content << ifs.rdbuf();
    rapidjson::Document doc;
    doc.Parse(content.str().c_str());
    return doc;
}

void expectVerbatimCopy(const char* definition, const char* tracker_file) {
    auto controller = readJson(TRACKER_CONTROLLER_SCHEMA_FILE);
    ASSERT_TRUE(controller.IsObject()) << TRACKER_CONTROLLER_SCHEMA_FILE;
    const char* defs_key = controller.HasMember("definitions") ? "definitions" : "$defs";
    const auto& expected = controller[defs_key][definition];

    auto copy = readJson(std::string(TRACKER_SCHEMA_DIR) + "/" + tracker_file);
    ASSERT_TRUE(copy.IsObject()) << tracker_file;
    for (const char* meta : {"$schema", "id", "$comment"}) {
        copy.RemoveMember(meta);
    }
    EXPECT_TRUE(copy == expected) << tracker_file << " differs from " << definition
                                  << " in controller/src/schema/metadata.schema.json";
}

TEST(PtzSchemaSyncTest, PoseContextSchemaMatchesController) {
    expectVerbatimCopy("pose_context", kPoseContextSchemaFile);
}

TEST(PtzSchemaSyncTest, PositioningStatusSchemaMatchesController) {
    expectVerbatimCopy("positioning_status", kPositioningStatusSchemaFile);
}

} // namespace
} // namespace tracker::ptz
