// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "logger.hpp"
#include "ptz_registry.hpp"
#include "ptz_test_utils.hpp"

#include <gtest/gtest.h>

#include <memory>

namespace tracker::ptz {
namespace {

using test::kBaseNs;
using test::ms;
using test::PoseJson;

class PtzRegistryTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::init("warn");
        scenes_ = {test::scene({test::camera(test::kSourceId, true), test::camera("static", false),
                                test::camera("unassigned-ptz", true)}),
                   test::scene({test::camera("other-ptz", true, std::nullopt)}, "scene-2")};
        assignments_ = {{test::kSourceId, test::kResolverId},
                        {"other-ptz", "resolver-b"},
                        {"not-in-any-scene", test::kResolverId}};
        registry_ = std::make_unique<PtzPoseRegistry>(scenes_, assignments_, test::dwellConfig(),
                                                      PtzMessageParser(TRACKER_SCHEMA_DIR),
                                                      [this] { return clock_; });
    }

    void TearDown() override { Logger::shutdown(); }

    /// Stationary poses every 100 ms; returns the timestamp of the last one.
    int64_t feedStationary(int count, int64_t start_sequence = 1, int64_t start_ns = kBaseNs) {
        int64_t timestamp = start_ns;
        for (int i = 0; i < count; ++i) {
            PoseJson json;
            json.sequence = start_sequence + i;
            json.timestamp_ns = start_ns + ms(100 * i);
            timestamp = json.timestamp_ns;
            EXPECT_EQ(registry_->onPoseMessage(test::poseTopic(), json.json()), std::nullopt);
        }
        return timestamp;
    }

    std::vector<Scene> scenes_;
    Assignments assignments_;
    PtzClockReading clock_{kBaseNs, true};
    std::unique_ptr<PtzPoseRegistry> registry_;
};

TEST_F(PtzRegistryTest, KnowsPtzCamerasAndSubscriptionScope) {
    EXPECT_TRUE(registry_->isPtzCamera(test::kSourceId));
    EXPECT_TRUE(registry_->isPtzCamera("unassigned-ptz"));
    EXPECT_FALSE(registry_->isPtzCamera("static"));
    EXPECT_FALSE(registry_->isPtzCamera("not-in-any-scene"));
    EXPECT_EQ(registry_->poseSourceIds(), (std::vector<std::string>{"other-ptz", test::kSourceId}));
    EXPECT_EQ(registry_->resolverIds(),
              (std::vector<std::string>{test::kResolverId, "resolver-b"}));
}

TEST_F(PtzRegistryTest, AdmitsAfterDwellWithPoseFieldsAndProjectionPose) {
    const auto last = feedStationary(4);
    clock_ = {last + ms(10), true};
    const auto admission = registry_->admit(test::kSourceId, last - ms(50));
    ASSERT_TRUE(admission.admitted);
    ASSERT_TRUE(admission.pose && admission.pose->view);
    EXPECT_EQ(admission.pose->sequence, 4);
    EXPECT_NEAR(admission.pose_age_s.value(), 0.01, 1e-12);
    EXPECT_NEAR(admission.timestamp_uncertainty_s.value(), 0.01, 1e-12);
    EXPECT_NEAR(admission.dwell_elapsed_s.value(), 0.3, 1e-12);
    EXPECT_EQ(admission.stationary_since_ns, kBaseNs);
}

TEST_F(PtzRegistryTest, UnsynchronizedClockFailsClosedAsSampleStale) {
    const auto last = feedStationary(4);
    const auto admission =
        registry_->admitAt(test::kSourceId, last - ms(50), {last + ms(10), false});
    EXPECT_FALSE(admission.admitted);
    EXPECT_EQ(admission.reason_detail, ReasonDetail::SampleStale);
    EXPECT_EQ(admission.invalid_reason, InvalidReason::PoseExpired);
    EXPECT_TRUE(admission.pose_age_s.has_value());
}

TEST_F(PtzRegistryTest, UnassignedPtzCameraIsRejectedAsUnmanaged) {
    const auto admission = registry_->admit("unassigned-ptz", kBaseNs);
    EXPECT_FALSE(admission.admitted);
    EXPECT_FALSE(admission.managed);
    EXPECT_EQ(admission.reason_detail, ReasonDetail::NoSample);
    EXPECT_FALSE(registry_->admit("unassigned-ptz", kBaseNs).admitted); // logged once
}

TEST_F(PtzRegistryTest, RoutesByTopicAndRejectsUnmanagedOrMalformedTopics) {
    PoseJson json;
    EXPECT_EQ(registry_->onPoseMessage("scenescape/positioning/pose/static", json.json()),
              PoseRejectStage::Unmanaged);
    EXPECT_EQ(registry_->onPoseMessage("scenescape/positioning/pose/unassigned-ptz", json.json()),
              PoseRejectStage::Unmanaged);
    EXPECT_EQ(registry_->onPoseMessage("scenescape/positioning/pose/a/b", json.json()),
              PoseRejectStage::Topic);
    EXPECT_EQ(registry_->onPoseMessage("scenescape/other/ptz-cam", json.json()),
              PoseRejectStage::Topic);
    EXPECT_EQ(registry_->onPoseMessage(test::poseTopic(), "{"), PoseRejectStage::Json);
}

TEST_F(PtzRegistryTest, PayloadNamingAnotherSourceResetsTheTopicSource) {
    const auto last = feedStationary(4);
    PoseJson foreign;
    foreign.source_id = "other-ptz";
    foreign.sequence = 5;
    foreign.timestamp_ns = last + ms(100);
    EXPECT_EQ(registry_->onPoseMessage(test::poseTopic(), foreign.json()), std::nullopt);
    const auto admission =
        registry_->admitAt(test::kSourceId, last - ms(50), {last + ms(10), true});
    EXPECT_FALSE(admission.admitted);
}

TEST_F(PtzRegistryTest, ResolverSessionChangeResetsAndStatusTopicMustMatch) {
    EXPECT_EQ(registry_->onStatusMessage(test::statusTopic(),
                                         test::statusJson(test::kResolverId, "online", kBaseNs)),
              std::nullopt);
    const auto last = feedStationary(4);
    EXPECT_TRUE(registry_->admitAt(test::kSourceId, last - ms(50), {last + ms(10), true}).admitted);

    EXPECT_EQ(registry_->onStatusMessage(test::statusTopic("resolver-b"),
                                         test::statusJson(test::kResolverId, "online", kBaseNs)),
              PoseRejectStage::Topic);
    EXPECT_EQ(registry_->onStatusMessage(test::statusTopic(), "nope"), PoseRejectStage::Json);
    EXPECT_TRUE(registry_->admitAt(test::kSourceId, last - ms(50), {last + ms(10), true}).admitted);

    EXPECT_EQ(
        registry_->onStatusMessage(test::statusTopic(),
                                   test::statusJson(test::kResolverId, "online", kBaseNs + ms(1))),
        std::nullopt);
    const auto after = registry_->admitAt(test::kSourceId, last - ms(50), {last + ms(10), true});
    EXPECT_EQ(after.reason_detail, ReasonDetail::DwellIncomplete);
}

TEST_F(PtzRegistryTest, FrameOfAnotherSceneFailsClosed) {
    PoseJson child_frame;
    child_frame.frame_id = "scene:child-scene";
    EXPECT_EQ(registry_->onPoseMessage(test::poseTopic(), child_frame.json()), std::nullopt);
    const auto admission = registry_->admitAt(test::kSourceId, kBaseNs, {kBaseNs + ms(10), true});
    EXPECT_EQ(admission.reason_detail, ReasonDetail::FrameMismatch);
}

TEST_F(PtzRegistryTest, CalibrationVersionIsPinnedOnlyWhenKnown) {
    PoseJson other_version;
    other_version.calibration_version = "cal-v2";
    EXPECT_EQ(registry_->onPoseMessage(test::poseTopic(), other_version.json()), std::nullopt);
    EXPECT_EQ(registry_->admitAt(test::kSourceId, kBaseNs, {kBaseNs + ms(10), true}).reason_detail,
              ReasonDetail::CalibrationChanged);

    // other-ptz has no calibration_version: any version is accepted (unpinned)
    for (int i = 0; i < 4; ++i) {
        PoseJson json;
        json.source_id = "other-ptz";
        json.frame_id = "scene:scene-2";
        json.calibration_version = "anything";
        json.sequence = i + 1;
        json.timestamp_ns = kBaseNs + ms(100 * i);
        EXPECT_EQ(registry_->onPoseMessage(test::poseTopic("other-ptz"), json.json()),
                  std::nullopt);
    }
    EXPECT_TRUE(
        registry_->admitAt("other-ptz", kBaseNs + ms(250), {kBaseNs + ms(310), true}).admitted);
}

TEST(PtzRegistryHelpersTest, TopicSegmentFrameAndDwellConfig) {
    EXPECT_EQ(topicSegment("scenescape/positioning/pose/cam", kPoseTopicPrefix), "cam");
    EXPECT_EQ(topicSegment("scenescape/positioning/pose/", kPoseTopicPrefix), "");
    EXPECT_EQ(topicSegment("x/cam", kPoseTopicPrefix), "");
    EXPECT_EQ(frameIdForScene("abc"), "scene:abc");
    PtzConfig config;
    config.max_pose_age_s = 0.5;
    config.max_detection_pipeline_latency_s = 1.0;
    config.max_detection_timestamp_uncertainty_s = 0.05;
    const auto dwell = dwellConfigFrom(config);
    EXPECT_EQ(dwell.max_pose_age_ns, 500'000'000);
    EXPECT_EQ(dwell.max_detection_pipeline_latency_ns, 1'000'000'000);
    EXPECT_EQ(dwell.max_detection_timestamp_uncertainty_ns, 50'000'000);
}

} // namespace
} // namespace tracker::ptz
