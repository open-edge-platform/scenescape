// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "logger.hpp"
#include "ptz_shadow.hpp"
#include "ptz_test_utils.hpp"
#include "utils/test_sink.hpp"

#include <gtest/gtest.h>

#include <rapidjson/document.h>

namespace tracker::ptz {
namespace {

using test::kBaseNs;
using test::ms;

class FixedResiduals : public ResidualSource {
public:
    explicit FixedResiduals(size_t count) : count_(count) {}
    [[nodiscard]] ShadowDetections compute() const override {
        ++calls;
        ShadowDetections out;
        for (size_t i = 0; i < count_; ++i) {
            out.push_back({"person", {0, 0, 0}, {0.5, 0, 0}, 0.5 + static_cast<double>(i)});
        }
        return out;
    }
    mutable int calls = 0;

private:
    size_t count_;
};

PoseSnapshotPtr pose(int64_t sequence, double yaw_deg = 0.0) {
    auto snapshot = std::make_shared<PoseSnapshot>();
    snapshot->source_id = test::kSourceId;
    snapshot->sequence = sequence;
    snapshot->calibration_version = test::kCalibration;
    snapshot->valid = true;
    const auto m = test::lookDownMatrix(yaw_deg);
    snapshot->view = PoseView::fromRigidMatrix(cv::Matx44d(m.data()));
    return snapshot;
}

PtzAdmission admitted(int64_t since_ns, int64_t sequence = 4, double yaw_deg = 0.0) {
    PtzAdmission admission;
    admission.admitted = true;
    admission.pose = pose(sequence, yaw_deg);
    admission.pose_age_s = 0.02;
    admission.timestamp_uncertainty_s = 0.01;
    admission.dwell_elapsed_s = 1.5;
    admission.stationary_since_ns = since_ns;
    return admission;
}

PtzAdmission rejected(ReasonDetail detail, bool managed = true) {
    PtzAdmission admission;
    admission.managed = managed;
    admission.reason_detail = detail;
    admission.invalid_reason = canonicalReason(detail);
    return admission;
}

DecisionContext context(const char* mode = "shadow", int64_t observation_ns = kBaseNs,
                        const PoseView* home = nullptr) {
    return DecisionContext{
        mode, test::kSceneUid, test::kSourceId, "2026-10-01T10:00:00.000000Z", observation_ns, 2,
        home};
}

TEST(PtzShadowRecorderTest, SamplesEveryNthPlusFirstDistinctDecisionPerWindow) {
    std::vector<std::string> lines;
    ShadowRecorder recorder("run-1", 3, [&lines](std::string_view l) { lines.emplace_back(l); });
    const auto ctx = context();
    // window 1: count 0 (emit), dup (skip), new detail (emit)
    EXPECT_TRUE(recorder.record(ctx, rejected(ReasonDetail::Moving), nullptr));
    EXPECT_FALSE(recorder.record(ctx, rejected(ReasonDetail::Moving), nullptr));
    EXPECT_TRUE(recorder.record(ctx, rejected(ReasonDetail::Settling), nullptr));
    // window 2 starts at count 3 regardless of decision
    EXPECT_TRUE(recorder.record(ctx, rejected(ReasonDetail::Settling), nullptr));
    EXPECT_TRUE(recorder.record(ctx, admitted(kBaseNs), nullptr));
    EXPECT_FALSE(recorder.record(ctx, admitted(kBaseNs), nullptr));
    EXPECT_EQ(lines.size(), 4u);

    // Independent per source
    auto other = ctx;
    other.source_id = "other";
    EXPECT_TRUE(recorder.record(other, rejected(ReasonDetail::Settling), nullptr));
}

TEST(PtzShadowRecorderTest, RecordHasControllerFieldsInOrderAndHarnessMarker) {
    std::vector<std::string> lines;
    ShadowRecorder recorder("run-1", 1, [&lines](std::string_view l) { lines.emplace_back(l); });
    FixedResiduals residuals(2);
    ASSERT_TRUE(recorder.record(context(), admitted(kBaseNs), &residuals));
    ASSERT_EQ(lines.size(), 1u);
    EXPECT_TRUE(lines[0].starts_with(R"({"record_type":"ptz_shadow","profile":"tracker")"));

    rapidjson::Document record;
    record.Parse(lines[0].c_str());
    ASSERT_TRUE(record.IsObject());
    const std::vector<std::string> expected_keys = {"record_type",
                                                    "profile",
                                                    "mode",
                                                    "run_id",
                                                    "scene_id",
                                                    "source_id",
                                                    "sequence",
                                                    "calibration_version",
                                                    "observation_timestamp",
                                                    "pose_age_s",
                                                    "timestamp_uncertainty_s",
                                                    "dwell_elapsed_s",
                                                    "admitted",
                                                    "managed",
                                                    "invalid_reason",
                                                    "reason_detail",
                                                    "detections"};
    std::vector<std::string> keys;
    for (auto it = record.MemberBegin(); it != record.MemberEnd(); ++it) {
        keys.emplace_back(it->name.GetString());
    }
    EXPECT_EQ(keys, expected_keys);
    EXPECT_STREQ(record["mode"].GetString(), "shadow");
    EXPECT_STREQ(record["run_id"].GetString(), "run-1");
    EXPECT_EQ(record["sequence"].GetInt(), 4);
    EXPECT_TRUE(record["admitted"].GetBool());
    EXPECT_TRUE(record["invalid_reason"].IsNull());
    EXPECT_TRUE(record["reason_detail"].IsNull());
    ASSERT_EQ(record["detections"].Size(), 2u);
    EXPECT_STREQ(record["detections"][0]["type"].GetString(), "person");
    EXPECT_DOUBLE_EQ(record["detections"][1]["residual_m"].GetDouble(), 1.5);
}

TEST(PtzShadowRecorderTest, RejectedRecordHasNullPoseFieldsAndCapsDetections) {
    ShadowRecorder recorder("run-1", 1, [](std::string_view) {});
    auto unmanaged = rejected(ReasonDetail::NoSample, false);
    rapidjson::Document record;
    record.Parse(recorder.formatRecord(context(), unmanaged, {}).c_str());
    EXPECT_TRUE(record["sequence"].IsNull());
    EXPECT_TRUE(record["calibration_version"].IsNull());
    EXPECT_TRUE(record["pose_age_s"].IsNull());
    EXPECT_FALSE(record["managed"].GetBool());
    EXPECT_STREQ(record["invalid_reason"].GetString(), "no_pose_available");
    EXPECT_STREQ(record["reason_detail"].GetString(), "no_sample");

    FixedResiduals many(kMaxRecordDetections + 10);
    record.Parse(recorder.formatRecord(context(), admitted(kBaseNs), many.compute()).c_str());
    EXPECT_EQ(record["detections"].Size(), kMaxRecordDetections);
}

TEST(PtzShadowRecorderTest, ResidualsAreComputedOnlyForEmittedRecords) {
    ShadowRecorder recorder("run-1", 10, [](std::string_view) {});
    FixedResiduals residuals(1);
    for (int i = 0; i < 10; ++i) {
        recorder.record(context(), admitted(kBaseNs), &residuals);
    }
    EXPECT_EQ(residuals.calls, 1);
}

TEST(PtzSummaryRecorderTest, LogsOncePerAppliedPoseWithPreviousPeriod) {
    std::vector<std::string> lines;
    SummaryRecorder recorder(1, [&lines](std::string_view l) { lines.emplace_back(l); });
    const auto home = PoseView::fromRigidMatrix(cv::Matx44d(test::lookDownMatrix(0.0).data()));
    FixedResiduals residuals(2);

    EXPECT_FALSE(recorder.record(context("shadow", kBaseNs, &home), rejected(ReasonDetail::Moving),
                                 nullptr));
    EXPECT_FALSE(recorder.record(context("shadow", kBaseNs + ms(500), &home),
                                 rejected(ReasonDetail::DwellIncomplete), nullptr));
    EXPECT_TRUE(recorder.record(context("shadow", kBaseNs + ms(1000), &home),
                                admitted(kBaseNs, 4, 30.0), &residuals));
    ASSERT_EQ(lines.size(), 1u);
    EXPECT_EQ(lines[0], "PTZ camera ptz-cam: pose applied (shadow); 30.00 deg from home, dwell "
                        "1.5 s, pose age 0.02 s; calibration=cal-v1; previous 0.5 s: 2 decisions, "
                        "0% admitted (rejected: moving 1, dwell_incomplete 1), 4 detections (0 "
                        "admitted)");

    // Same dwell: no new line. New dwell: summary includes admitted decisions and residuals.
    EXPECT_FALSE(recorder.record(context("shadow", kBaseNs + ms(1100), &home),
                                 admitted(kBaseNs, 5, 30.0), &residuals));
    EXPECT_TRUE(recorder.record(context("shadow", kBaseNs + ms(3000), &home),
                                admitted(kBaseNs + ms(2000), 9, 0.0), &residuals));
    ASSERT_EQ(lines.size(), 2u);
    EXPECT_EQ(lines[1], "PTZ camera ptz-cam: pose applied (shadow); 0.00 deg from home, dwell 1.5 "
                        "s, pose age 0.02 s; calibration=cal-v1; previous 0.1 s: 2 decisions, 100% "
                        "admitted, 4 detections (4 admitted), residual median 1.00 m, p95 1.50 m, "
                        "max 1.50 m");
}

TEST(PtzSummaryRecorderTest, UnknownOffsetAndTranslation) {
    std::vector<std::string> lines;
    SummaryRecorder recorder(1, [&lines](std::string_view l) { lines.emplace_back(l); });
    recorder.record(context("enforce"), admitted(kBaseNs), nullptr);
    ASSERT_EQ(lines.size(), 1u);
    EXPECT_NE(lines[0].find("offset from home unknown"), std::string::npos);
    EXPECT_NE(lines[0].find("no earlier decisions"), std::string::npos);

    auto home = PoseView::fromRigidMatrix(cv::Matx44d(test::lookDownMatrix(0.0, 2.0).data()));
    auto ctx = context("enforce", kBaseNs, &home);
    recorder.record(ctx, admitted(kBaseNs + 1), nullptr);
    EXPECT_NE(lines[1].find("1.000 m from home position"), std::string::npos) << lines[1];
}

TEST(PtzShadowMathTest, OffsetAndPercentile) {
    const auto home = PoseView::fromRigidMatrix(cv::Matx44d(test::lookDownMatrix(0.0).data()));
    const auto turned = PoseView::fromRigidMatrix(cv::Matx44d(test::lookDownMatrix(45.0).data()));
    const auto [rotation, translation] = offsetFromHome(home, turned);
    EXPECT_NEAR(rotation, 45.0, 1e-9);
    EXPECT_NEAR(translation, 0.0, 1e-12);
    EXPECT_DOUBLE_EQ(percentile({}, 0.5), 0.0);
    EXPECT_DOUBLE_EQ(percentile({1.0, 2.0, 3.0, 4.0}, 0.5), 2.5);
    EXPECT_DOUBLE_EQ(percentile({1.0, 2.0, 3.0, 4.0}, 0.95), 3.85);
}

TEST(PtzRawLineTest, RawLinesBypassTheJsonEnvelopeAndLogLevel) {
    auto sink =
        quill::Frontend::create_or_get_sink<tracker::test::TestSink>("ptz_raw_line_test_sink");
    auto* test_sink = static_cast<tracker::test::TestSink*>(sink.get());
    Logger::init("error", sink);
    Logger::raw_line(R"({"record_type":"ptz_shadow","x":1})");
    Logger::shutdown();
    const auto statements = test_sink->get_statements();
    ASSERT_FALSE(statements.empty());
    EXPECT_EQ(statements.back(), R"({"record_type":"ptz_shadow","x":1})");
    Logger::raw_line("ignored after shutdown");
}

TEST(PtzRawLineTest, DefaultSinksAreSafeWithoutLogger) {
    ShadowRecorder shadow("run", 1);
    EXPECT_TRUE(shadow.record(context(), rejected(ReasonDetail::Moving), nullptr));
}

} // namespace
} // namespace tracker::ptz
