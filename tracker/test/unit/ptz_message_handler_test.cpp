// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "logger.hpp"
#include "message_handler.hpp"
#include "ptz_consumer.hpp"
#include "ptz_test_utils.hpp"
#include "scene_registry.hpp"
#include "time_chunk_buffer.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <memory>

namespace tracker {
namespace {

using ptz::test::iso;
using ptz::test::kBaseNs;
using ptz::test::ms;
using ptz::test::PoseJson;

constexpr const char* kCategory = "person";

class FakeMqttClient : public IMqttClient {
public:
    void connect() override {}
    void disconnect(std::chrono::milliseconds) override {}
    void subscribe(const std::string& topic) override { subscribed.push_back(topic); }
    void unsubscribe(const std::string& topic) override { unsubscribed.push_back(topic); }
    void publish(const std::string&, const std::string&) override {}
    void setMessageCallback(MessageCallback callback) override { callback_ = std::move(callback); }
    [[nodiscard]] bool isConnected() const override { return true; }
    [[nodiscard]] bool isSubscribed() const override { return true; }

    void deliver(const std::string& topic, const std::string& payload) {
        if (callback_) {
            callback_(topic, payload);
        }
    }

    std::vector<std::string> subscribed;
    std::vector<std::string> unsubscribed;

private:
    MessageCallback callback_;
};

struct RecordedDecision {
    std::string source_id;
    bool admitted = false;
    ptz::ReasonDetail detail = ptz::ReasonDetail::None;
    size_t residuals = 0;
    bool had_residual_source = false;
};

class CapturingRecorder : public ptz::DecisionRecorder {
public:
    bool record(const ptz::DecisionContext& context, const ptz::PtzAdmission& admission,
                const ptz::ResidualSource* residuals) override {
        RecordedDecision decision{std::string(context.source_id), admission.admitted,
                                  admission.reason_detail, 0, residuals != nullptr};
        if (residuals) {
            const auto computed = residuals->compute();
            decision.residuals = computed.size();
            last_residuals = computed;
        }
        decisions->push_back(decision);
        return true;
    }

    std::shared_ptr<std::vector<RecordedDecision>> decisions =
        std::make_shared<std::vector<RecordedDecision>>();
    ptz::ShadowDetections last_residuals;
};

std::string detectionMessage(const std::string& camera_id, int64_t timestamp_ns, int count = 1) {
    std::string detections;
    for (int i = 0; i < count; ++i) {
        detections += (i ? "," : "") + std::string(R"({"id":)") + std::to_string(i) +
                      R"(,"bounding_box_px":{"x":300,"y":200,"width":40,"height":80}})";
    }
    return R"({"id":")" + camera_id + R"(","timestamp":")" + iso(timestamp_ns) +
           R"(","objects":{")" + kCategory + R"(":[)" + detections + "]}}";
}

class PtzMessageHandlerTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::init("warn");
        scenes_ = {ptz::test::scene({ptz::test::camera(ptz::test::kSourceId, true),
                                     ptz::test::camera("static-cam", false),
                                     ptz::test::camera("unassigned-ptz", true)})};
        registry_.register_scenes(scenes_);
        config_.max_lag_s = 1e9;
    }

    void TearDown() override {
        if (handler_) {
            handler_->stop();
        }
        Logger::shutdown();
    }

    void start(PtzMode mode) {
        if (mode != PtzMode::Off) {
            auto recorder = std::make_unique<CapturingRecorder>();
            recorder_ = recorder.get();
            auto pose_registry = std::make_shared<ptz::PtzPoseRegistry>(
                scenes_, ptz::Assignments{{ptz::test::kSourceId, ptz::test::kResolverId}},
                ptz::test::dwellConfig(0.5, 0.2, 0.0), ptz::PtzMessageParser(TRACKER_SCHEMA_DIR),
                [this] { return clock_; });
            consumer_ = std::make_shared<ptz::PtzConsumer>(mode, pose_registry, std::move(recorder),
                                                           scenes_);
        }
        handler_ =
            std::make_unique<MessageHandler>(client_, registry_, buffer_, config_, false,
                                             TRACKER_SCHEMA_DIR, makeSystemClock(), consumer_);
        handler_->start();
    }

    /// Stationary poses every 100 ms; returns the last pose timestamp.
    int64_t parkCamera(int count, int64_t start_ns = kBaseNs) {
        int64_t last = start_ns;
        for (int i = 0; i < count; ++i) {
            PoseJson json;
            json.sequence = i + 1;
            json.timestamp_ns = start_ns + ms(100 * i);
            json.matrix = ptz::test::lookDownMatrix(20.0);
            last = json.timestamp_ns;
            client_->deliver(ptz::test::poseTopic(), json.json());
        }
        return last;
    }

    const CameraSlot* slot(BufferMap& snapshot, const std::string& camera_id) {
        auto scope = snapshot.find(TrackingScope{ptz::test::kSceneUid, kCategory});
        if (scope == snapshot.end()) {
            return nullptr;
        }
        auto it = scope->second.find(camera_id);
        return it == scope->second.end() ? nullptr : &it->second;
    }

    std::vector<Scene> scenes_;
    SceneRegistry registry_;
    TimeChunkBuffer buffer_;
    TrackingConfig config_;
    std::shared_ptr<FakeMqttClient> client_ = std::make_shared<FakeMqttClient>();
    std::shared_ptr<ptz::PtzConsumer> consumer_;
    CapturingRecorder* recorder_ = nullptr;
    std::unique_ptr<MessageHandler> handler_;
    ptz::PtzClockReading clock_{kBaseNs, true};
};

TEST_F(PtzMessageHandlerTest, OffModeAddsNoSubscriptionsAndKeepsStaticBatches) {
    start(PtzMode::Off);
    EXPECT_TRUE(
        std::none_of(client_->subscribed.begin(), client_->subscribed.end(),
                     [](const auto& t) { return t.starts_with("scenescape/positioning/"); }));
    client_->deliver("scenescape/data/camera/ptz-cam", detectionMessage("ptz-cam", kBaseNs));
    auto snapshot = buffer_.pop_all();
    const auto* ptz_slot = slot(snapshot, "ptz-cam");
    ASSERT_NE(ptz_slot, nullptr);
    EXPECT_EQ(ptz_slot->latest.detections.size(), 1u);
    EXPECT_FALSE(ptz_slot->latest.ptz_preserve);
    EXPECT_EQ(ptz_slot->latest.ptz_pose, nullptr);
}

TEST_F(PtzMessageHandlerTest, SubscribesOnlyToAssignedSourcesAndTheirResolvers) {
    start(PtzMode::Enforce);
    const auto& subs = client_->subscribed;
    EXPECT_NE(std::find(subs.begin(), subs.end(), "scenescape/positioning/pose/ptz-cam"),
              subs.end());
    EXPECT_NE(std::find(subs.begin(), subs.end(), "scenescape/positioning/status/positioning"),
              subs.end());
    const auto positioning = std::count_if(subs.begin(), subs.end(), [](const auto& t) {
        return t.starts_with("scenescape/positioning/");
    });
    EXPECT_EQ(positioning, 2);
    handler_->stop();
    const auto& unsubs = client_->unsubscribed;
    EXPECT_NE(std::find(unsubs.begin(), unsubs.end(), "scenescape/positioning/pose/ptz-cam"),
              unsubs.end());
    handler_.reset();
}

TEST_F(PtzMessageHandlerTest, EnforceGatesRejectedBatchesAsHeartbeats) {
    start(PtzMode::Enforce);
    client_->deliver("scenescape/data/camera/ptz-cam", detectionMessage("ptz-cam", kBaseNs));
    EXPECT_EQ(handler_->getPtzGatedCount(), 1);
    ASSERT_EQ(recorder_->decisions->size(), 1u);
    EXPECT_EQ(recorder_->decisions->back().detail, ptz::ReasonDetail::NoSample);

    auto snapshot = buffer_.pop_all();
    const auto* gated = slot(snapshot, "ptz-cam");
    ASSERT_NE(gated, nullptr);
    EXPECT_TRUE(gated->latest.ptz_gated);
    EXPECT_TRUE(gated->latest.detections.empty());
    EXPECT_EQ(gated->latest.ptz_pose, nullptr);
}

TEST_F(PtzMessageHandlerTest, EnforceAdmitsAfterDwellWithThePose) {
    start(PtzMode::Enforce);
    const auto last = parkCamera(4);
    clock_ = {last + ms(20), true};
    client_->deliver("scenescape/data/camera/ptz-cam", detectionMessage("ptz-cam", last - ms(40)));
    client_->deliver("scenescape/data/camera/static-cam",
                     detectionMessage("static-cam", last - ms(40)));
    EXPECT_EQ(handler_->getPtzGatedCount(), 0);
    ASSERT_EQ(recorder_->decisions->size(), 1u); // static camera is not a PTZ decision
    EXPECT_TRUE(recorder_->decisions->back().admitted);
    EXPECT_FALSE(recorder_->decisions->back().had_residual_source); // enforce: no shadow work

    auto snapshot = buffer_.pop_all();
    const auto* admitted = slot(snapshot, "ptz-cam");
    ASSERT_NE(admitted, nullptr);
    ASSERT_NE(admitted->latest.ptz_pose, nullptr);
    EXPECT_EQ(admitted->latest.ptz_pose->sequence, 4);
    EXPECT_TRUE(admitted->latest.ptz_preserve);
    EXPECT_EQ(admitted->latest.detections.size(), 1u);
    const auto* static_slot = slot(snapshot, "static-cam");
    ASSERT_NE(static_slot, nullptr);
    EXPECT_FALSE(static_slot->latest.ptz_preserve);
    EXPECT_EQ(static_slot->latest.ptz_pose, nullptr);
}

TEST_F(PtzMessageHandlerTest, ObservationTimeIsTheAcquisitionTimestampNotArrival) {
    start(PtzMode::Enforce);
    const auto last = parkCamera(4);
    clock_ = {last + ms(20), true};
    // Acquired after the latest stationary pose: the pose at acquisition is unknown.
    client_->deliver("scenescape/data/camera/ptz-cam", detectionMessage("ptz-cam", last + ms(10)));
    ASSERT_EQ(recorder_->decisions->size(), 1u);
    EXPECT_EQ(recorder_->decisions->back().detail, ptz::ReasonDetail::NoSample);
    EXPECT_EQ(handler_->getPtzGatedCount(), 1);
}

TEST_F(PtzMessageHandlerTest, SameCameraBatchesWithDistinctTimestampsKeepTheirOwnDecision) {
    start(PtzMode::Enforce);
    const auto last = parkCamera(4);
    clock_ = {last + ms(20), true};
    client_->deliver("scenescape/data/camera/ptz-cam", detectionMessage("ptz-cam", last - ms(60)));
    client_->deliver("scenescape/data/camera/ptz-cam",
                     detectionMessage("ptz-cam", last - ms(30), 2));
    // A rejected (newer than pose) batch must not displace the admitted ones
    client_->deliver("scenescape/data/camera/ptz-cam", detectionMessage("ptz-cam", last + ms(15)));

    auto snapshot = buffer_.pop_all();
    const auto* batches = slot(snapshot, "ptz-cam");
    ASSERT_NE(batches, nullptr);
    ASSERT_EQ(batches->earlier.size(), 1u);
    EXPECT_EQ(batches->earlier[0].detections.size(), 1u);
    EXPECT_EQ(batches->latest.detections.size(), 2u);
    EXPECT_NE(batches->earlier[0].ptz_pose, nullptr);
    EXPECT_NE(batches->latest.ptz_pose, nullptr);
    EXPECT_FALSE(batches->latest.ptz_gated);
}

TEST_F(PtzMessageHandlerTest, ShadowNeverChangesBatchesAndComputesResiduals) {
    start(PtzMode::Shadow);
    client_->deliver("scenescape/data/camera/ptz-cam", detectionMessage("ptz-cam", kBaseNs));
    const auto last = parkCamera(4, kBaseNs + ms(10));
    clock_ = {last + ms(20), true};
    client_->deliver("scenescape/data/camera/ptz-cam",
                     detectionMessage("ptz-cam", last - ms(40), 3));
    EXPECT_EQ(handler_->getPtzGatedCount(), 0);
    ASSERT_EQ(recorder_->decisions->size(), 2u);
    EXPECT_FALSE(recorder_->decisions->at(0).admitted);
    EXPECT_FALSE(recorder_->decisions->at(0).had_residual_source);
    EXPECT_TRUE(recorder_->decisions->at(1).admitted);
    EXPECT_EQ(recorder_->decisions->at(1).residuals, 3u);
    for (const auto& residual : recorder_->last_residuals) {
        EXPECT_EQ(residual.type, kCategory);
        EXPECT_GT(residual.residual_m, 0.0); // 20 deg yaw moves the projection
    }

    auto snapshot = buffer_.pop_all();
    const auto* batches = slot(snapshot, "ptz-cam");
    ASSERT_NE(batches, nullptr);
    EXPECT_TRUE(batches->earlier.empty()); // keep-latest, as with PTZ off
    EXPECT_EQ(batches->latest.detections.size(), 3u);
    EXPECT_FALSE(batches->latest.ptz_preserve);
    EXPECT_FALSE(batches->latest.ptz_gated);
    EXPECT_EQ(batches->latest.ptz_pose, nullptr);
}

TEST_F(PtzMessageHandlerTest, UnassignedPtzCameraIsGatedInEnforceMode) {
    start(PtzMode::Enforce);
    client_->deliver("scenescape/data/camera/unassigned-ptz",
                     detectionMessage("unassigned-ptz", kBaseNs));
    EXPECT_EQ(handler_->getPtzGatedCount(), 1);
}

TEST_F(PtzMessageHandlerTest, PositioningTopicsAreConsumedNotTreatedAsCameras) {
    start(PtzMode::Enforce);
    const int rejected_before = handler_->getRejectedCount();
    client_->deliver(ptz::test::statusTopic(),
                     ptz::test::statusJson(ptz::test::kResolverId, "online", kBaseNs));
    client_->deliver(ptz::test::poseTopic(), "{bad");
    client_->deliver("scenescape/positioning/unknown/x", "{}");
    EXPECT_EQ(handler_->getRejectedCount(), rejected_before);
    EXPECT_EQ(handler_->getReceivedCount(), 0);
}

TEST(PtzConsumerTest, ModeNames) {
    EXPECT_STREQ(ptz::toString(PtzMode::Enforce), "enforce");
    EXPECT_STREQ(ptz::toString(PtzMode::Shadow), "shadow");
    EXPECT_STREQ(ptz::toString(PtzMode::Off), "off");
}

} // namespace
} // namespace tracker
