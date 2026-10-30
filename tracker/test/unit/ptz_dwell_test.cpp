// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_dwell.hpp"
#include "ptz_test_utils.hpp"
#include "ptz_time.hpp"

#include <gtest/gtest.h>

#include <memory>

namespace tracker::ptz {
namespace {

using test::kBaseNs;
using test::ms;

// --- Timestamps ---

TEST(PtzTimeTest, ParsesMicrosecondsExactly) {
    auto base = parseIsoTimestampNs("2026-10-01T10:00:00.000000Z");
    auto plus_one = parseIsoTimestampNs("2026-10-01T10:00:00.000001Z");
    ASSERT_TRUE(base && plus_one);
    EXPECT_EQ(*plus_one - *base, 1000);
    EXPECT_EQ(*base, 1790848800LL * kNsPerS);
}

TEST(PtzTimeTest, TruncatesBeyondMicrosecondsLikePython) {
    auto truncated = parseIsoTimestampNs("2026-10-01T10:00:00.1234569Z");
    auto exact = parseIsoTimestampNs("2026-10-01T10:00:00.123456Z");
    ASSERT_TRUE(truncated && exact);
    EXPECT_EQ(*truncated, *exact);
}

TEST(PtzTimeTest, AcceptsOffsetsAndShortFractions) {
    auto utc = parseIsoTimestampNs("2026-10-01T10:00:00.5Z");
    auto offset = parseIsoTimestampNs("2026-10-01T12:00:00.500+02:00");
    auto negative = parseIsoTimestampNs("2026-10-01T09:30:00.5-00:30");
    auto space = parseIsoTimestampNs("2026-10-01 10:00:00.5z");
    ASSERT_TRUE(utc && offset && negative && space);
    EXPECT_EQ(*utc, *offset);
    EXPECT_EQ(*utc, *negative);
    EXPECT_EQ(*utc, *space);
}

TEST(PtzTimeTest, RejectsInvalidTimestamps) {
    for (const char* text :
         {"", "2026-10-01T10:00:00", "2026-10-01T10:00:00.Z", "2026-13-01T10:00:00Z",
          "2026-02-30T10:00:00Z", "2026-10-01T24:00:00Z", "2026-10-01T10:60:00Z",
          "2026-10-01T10:00:60Z", "2026-10-01T10:00:00+2:00", "2026-10-01T10:00:00+24:00",
          "2026-10-01T10:00:00Zjunk", "26-10-01T10:00:00Z", "2026/10/01T10:00:00Z",
          "2026-10-01X10:00:00Z", "2026-10-01T10-00:00Z"}) {
        EXPECT_FALSE(parseIsoTimestampNs(text).has_value()) << text;
    }
}

TEST(PtzTimeTest, SecondsToNsRoundsHalfToEven) {
    EXPECT_EQ(secondsToNs(0.05), 50'000'000);
    EXPECT_EQ(secondsToNs(1.0), kNsPerS);
    EXPECT_EQ(secondsToNs(2.5e-9), 2);
    EXPECT_EQ(secondsToNs(3.5e-9), 4);
}

// --- Reason mapping ---

TEST(PtzReasonTest, RoundTripsEveryDetailAndMapsCanonicalReason) {
    for (size_t i = 1; i < kReasonDetailCount; ++i) {
        const auto detail = static_cast<ReasonDetail>(i);
        EXPECT_EQ(parseReasonDetail(toString(detail)), detail);
    }
    EXPECT_EQ(canonicalReason(ReasonDetail::NoSample), InvalidReason::NoPoseAvailable);
    EXPECT_EQ(canonicalReason(ReasonDetail::SampleStale), InvalidReason::PoseExpired);
    EXPECT_EQ(canonicalReason(ReasonDetail::DetectionTooOld), InvalidReason::PoseExpired);
    EXPECT_EQ(canonicalReason(ReasonDetail::FrameMismatch), InvalidReason::InvalidPose);
    EXPECT_FALSE(parseReasonDetail("bogus").has_value());
    EXPECT_FALSE(parseInvalidReason("bogus").has_value());
    EXPECT_FALSE(parseMotionState("bogus").has_value());
    EXPECT_STREQ(toString(InvalidReason::None), "");
}

// --- DwellTracker ---

PoseSnapshotPtr stationary(int64_t sequence, int64_t timestamp_ns, int64_t uncertainty_ns = 0) {
    auto pose = std::make_shared<PoseSnapshot>();
    pose->source_id = test::kSourceId;
    pose->sequence = sequence;
    pose->timestamp_ns = timestamp_ns;
    pose->valid_until_ns = timestamp_ns + ms(1000);
    pose->timestamp_uncertainty_ns = uncertainty_ns;
    pose->valid = true;
    pose->motion_state = MotionState::Stationary;
    pose->calibration_version = test::kCalibration;
    pose->frame_id = "scene:scene-1";
    pose->view = PoseView::fromRigidMatrix(cv::Matx44d::eye());
    return pose;
}

DwellTracker makeTracker() {
    return DwellTracker(test::kSourceId, test::kResolverId, test::dwellConfig(0.5, 0.2, 0.0),
                        std::string("scene:scene-1"), std::string(test::kCalibration));
}

/// Feed stationary poses every 100 ms from kBaseNs up to and including @p last.
void feed(DwellTracker& tracker, int last) {
    for (int i = 0; i <= last; ++i) {
        tracker.onPose(stationary(i + 1, kBaseNs + ms(100 * i)));
    }
}

TEST(PtzDwellTest, AdmitsOnlyAfterFullDwellAndWithinBounds) {
    auto tracker = makeTracker();
    feed(tracker, 1);
    auto early = tracker.evaluate(kBaseNs + ms(50), kBaseNs + ms(110));
    EXPECT_EQ(early.reason_detail, ReasonDetail::DwellIncomplete);

    tracker.onPose(stationary(3, kBaseNs + ms(200)));
    tracker.onPose(stationary(4, kBaseNs + ms(300)));
    auto admitted = tracker.evaluate(kBaseNs + ms(250), kBaseNs + ms(310));
    EXPECT_TRUE(admitted.admitted);
    ASSERT_TRUE(admitted.dwell_elapsed_s.has_value());
    EXPECT_DOUBLE_EQ(*admitted.dwell_elapsed_s, 0.3);
    EXPECT_EQ(tracker.stationarySinceNs(), kBaseNs);

    // Observation newer than the latest stationary pose, and a detection that is too old
    EXPECT_EQ(tracker.evaluate(kBaseNs + ms(301), kBaseNs + ms(310)).reason_detail,
              ReasonDetail::NoSample);
    EXPECT_EQ(tracker.evaluate(kBaseNs + ms(100), kBaseNs + ms(301) + ms(200)).reason_detail,
              ReasonDetail::DetectionTooOld);
    EXPECT_EQ(tracker.evaluate(kBaseNs - 1, kBaseNs + ms(150)).reason_detail,
              ReasonDetail::ObservationBeforeDwell);
}

TEST(PtzDwellTest, ResetsOnGapTimestampAndInvalidPose) {
    auto tracker = makeTracker();
    feed(tracker, 3);
    tracker.onPose(stationary(10, kBaseNs + ms(400))); // sequence gap
    EXPECT_EQ(tracker.stationarySinceNs(), kBaseNs + ms(400));

    tracker.onPose(stationary(11, kBaseNs + ms(400))); // non-increasing timestamp
    EXPECT_EQ(tracker.stationarySinceNs(), kBaseNs + ms(400));

    auto moving = std::make_shared<PoseSnapshot>(*stationary(12, kBaseNs + ms(500)));
    moving->motion_state = MotionState::Slewing;
    tracker.onPose(moving);
    EXPECT_FALSE(tracker.stationarySinceNs().has_value());
    EXPECT_EQ(tracker.evaluate(kBaseNs, kBaseNs + ms(510)).reason_detail, ReasonDetail::Moving);
}

TEST(PtzDwellTest, InvalidPoseWithoutDetailReportsItsReason) {
    auto tracker = makeTracker();
    auto invalid = std::make_shared<PoseSnapshot>(*stationary(1, kBaseNs));
    invalid->valid = false;
    invalid->view.reset();
    invalid->invalid_reason = InvalidReason::PoseExpired;
    tracker.onPose(invalid);
    auto decision = tracker.evaluate(kBaseNs, kBaseNs + ms(10));
    EXPECT_FALSE(decision.admitted);
    EXPECT_EQ(decision.invalid_reason, InvalidReason::PoseExpired);
    EXPECT_EQ(decision.reason_detail, ReasonDetail::None);
}

TEST(PtzDwellTest, CalibrationChangeAndUnknownMotion) {
    auto tracker = makeTracker();
    feed(tracker, 3);
    tracker.setExpectedCalibrationVersion(std::string("cal-v2"));
    EXPECT_FALSE(tracker.stationarySinceNs().has_value());
    EXPECT_EQ(tracker.evaluate(kBaseNs, kBaseNs + ms(310)).reason_detail,
              ReasonDetail::CalibrationChanged);
    tracker.setExpectedCalibrationVersion(std::string("cal-v2")); // unchanged: no reset

    auto unknown = std::make_shared<PoseSnapshot>(*stationary(5, kBaseNs + ms(400)));
    unknown->motion_state = MotionState::Unknown;
    tracker.onPose(unknown);
    EXPECT_EQ(tracker.evaluate(kBaseNs, kBaseNs + ms(410)).reason_detail, ReasonDetail::NoSample);
}

TEST(PtzDwellTest, StatusFromOtherResolverIsIgnoredAndNullPoseIsSafe) {
    auto tracker = makeTracker();
    tracker.onStatus(test::kResolverId, true, kBaseNs);
    feed(tracker, 3);
    tracker.onStatus("other-resolver", false, kBaseNs);
    EXPECT_EQ(tracker.stationarySinceNs(), kBaseNs);
    tracker.onStatus(test::kResolverId, true, kBaseNs);
    EXPECT_EQ(tracker.stationarySinceNs(), kBaseNs);
    tracker.onPose(nullptr);
    EXPECT_EQ(tracker.stationarySinceNs(), kBaseNs);
    EXPECT_EQ(tracker.sourceId(), test::kSourceId);
    EXPECT_EQ(tracker.expectedFrameId(), std::string("scene:scene-1"));
    EXPECT_EQ(tracker.expectedCalibrationVersion(), std::string(test::kCalibration));
}

} // namespace
} // namespace tracker::ptz
