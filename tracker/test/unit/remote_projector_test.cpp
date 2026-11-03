// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "remote_projector.hpp"

#include "config_loader.hpp"
#include "logger.hpp"
#include "metrics.hpp"
#include "telemetry.hpp"

#include <cmath>
#include <functional>
#include <limits>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

#include <gtest/gtest.h>
#include <opentelemetry/exporters/memory/in_memory_metric_data.h>
#include <opentelemetry/exporters/memory/in_memory_metric_exporter_factory.h>
#include <opentelemetry/sdk/metrics/data/point_data.h>

namespace tracker {
namespace {

namespace metrics_sdk = opentelemetry::sdk::metrics;
namespace memory = opentelemetry::exporter::memory;

using rv::tracking::TrackedObject;

constexpr double kLocalYaw = 0.3;
constexpr double kHeight = 1.7;

// Local geometry: x = 100 + detection index, yaw and has_orientation set. Camera "unknown" cannot
// be projected; detections with id 99 have no local geometry.
class FakeLocalProjector final : public DetectionProjector {
public:
    std::vector<std::optional<ProjectedDetections>>
    project(std::span<const DetectionBatch> batches) override {
        std::vector<std::optional<ProjectedDetections>> projected;
        for (const auto& batch : batches) {
            if (batch.camera_id == "unknown") {
                projected.emplace_back();
                continue;
            }
            ProjectedDetections geometry{std::vector<TrackedObject>(batch.detections.size()),
                                         std::vector<uint8_t>(batch.detections.size(), 0)};
            for (size_t d = 0; d < batch.detections.size(); ++d) {
                if (batch.detections[d].id == 99) {
                    continue;
                }
                auto& object = geometry.objects[d];
                object.x = 100.0 + static_cast<double>(d);
                object.length = object.width = 0.4;
                object.height = 1.5;
                object.yaw = kLocalYaw;
                object.attributes["has_orientation"] = "1";
                geometry.has_geometry[d] = 1;
            }
            projected.emplace_back(std::move(geometry));
        }
        return projected;
    }
};

// Dense SPD R: position cross terms plus x-length, y-width, z-height and length-yaw terms.
std::vector<double> denseR() {
    return {0.040,  0.015,  -0.008, 0.002, 0.000, 0.000,  0.000, //
            0.015,  0.040,  -0.006, 0.000, 0.001, 0.000,  0.000, //
            -0.008, -0.006, 0.250,  0.000, 0.000, -0.030, 0.000, //
            0.002,  0.000,  0.000,  0.200, 0.000, 0.000,  0.010, //
            0.000,  0.001,  0.000,  0.000, 0.200, 0.000,  0.000, //
            0.000,  0.000,  -0.030, 0.000, 0.000, 0.200,  0.000, //
            0.000,  0.000,  0.000,  0.010, 0.000, 0.000,  0.200};
}

// Remote measurement k: centre (10 + k, 20 + k, height / 2), size 0.5 x 0.6 x height.
RemoteMeasurement goodMeasurement(size_t k) {
    const double offset = static_cast<double>(k);
    return {std::to_string(k),
            false,
            {10.0 + offset, 20.0 + offset, kHeight / 2.0, 0.5, 0.6, kHeight, 0.0},
            denseR()};
}

ProjectionReply goodReply(const ProjectionFrame& frame) {
    ProjectionReply reply;
    for (size_t k = 0; k < frame.boxes.size(); ++k) {
        reply.measurements.push_back(goodMeasurement(k));
    }
    return reply;
}

class FakeClient final : public ProjectionClient {
public:
    using ReplyFn = std::function<ProjectionReply(const ProjectionFrame&)>;

    explicit FakeClient(ReplyFn reply_fn = goodReply) : reply_fn_(std::move(reply_fn)) {}

    std::vector<ProjectionReply> projectFrames(const std::string& scene_id,
                                               const std::string& category, ConditioningMode mode,
                                               std::span<const ProjectionFrame> frames) override {
        ++calls;
        last_scene_id = scene_id;
        last_category = category;
        last_mode = mode;
        last_frames.assign(frames.begin(), frames.end());
        if (throw_error) {
            throw std::runtime_error("transport broke");
        }
        std::vector<ProjectionReply> replies;
        for (const auto& frame : frames) {
            replies.push_back(reply_fn_(frame));
        }
        if (drop_last_reply && !replies.empty()) {
            replies.pop_back();
        }
        return replies;
    }

    int calls = 0;
    std::string last_scene_id;
    std::string last_category;
    ConditioningMode last_mode = ConditioningMode::Auto;
    std::vector<ProjectionFrame> last_frames;
    bool throw_error = false;
    bool drop_last_reply = false;

private:
    ReplyFn reply_fn_;
};

Detection pixelDetection(int32_t id = 1) {
    return Detection{.id = id, .bounding_box_px = cv::Rect2f(10.0f, 20.0f, 50.0f, 100.0f)};
}

Detection translationDetection() {
    Detection detection;
    detection.translation = std::array<double, 3>{1.0, 2.0, 3.0};
    detection.size = std::array<double, 3>{0.5, 0.5, 1.8};
    return detection;
}

DetectionBatch makeBatch(const std::string& camera_id, std::vector<Detection> detections) {
    DetectionBatch batch;
    batch.camera_id = camera_id;
    batch.timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(1'500));
    batch.detections = std::move(detections);
    return batch;
}

class RemoteProjectorTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::init("error");
        Metrics::reset();
        metric_data_ = std::make_shared<memory::SimpleAggregateInMemoryMetricData>();
        ServiceConfig config;
        config.observability.metrics.enabled = true;
        config.observability.metrics.export_interval_s = 1;
        Telemetry::init(config, memory::InMemoryMetricExporterFactory::Create(metric_data_));
    }

    void TearDown() override {
        Telemetry::shutdown();
        Metrics::reset();
        Logger::shutdown();
    }

    RemoteProjector makeProjector(std::shared_ptr<FakeClient> client,
                                  ConditioningMode mode = ConditioningMode::Auto) {
        return RemoteProjector({"scene-uid", "person"}, std::make_unique<FakeLocalProjector>(),
                               std::move(client), mode);
    }

    /// Failed calls with `reason`; flushes telemetry, so call once at the end of a test.
    int64_t failedCalls(const std::string& reason) {
        Telemetry::shutdown();
        int64_t total = 0;
        for (const auto& [attributes, point] :
             metric_data_->Get(kMeterName, kMetricRemoteProjectionFailedCalls)) {
            const auto found = attributes.find(kAttrReason);
            if (found == attributes.end() || std::get<std::string>(found->second) != reason) {
                continue;
            }
            EXPECT_EQ(std::get<std::string>(attributes.at(kAttrScene)), "scene-uid");
            EXPECT_EQ(std::get<std::string>(attributes.at(kAttrCategory)), "person");
            const auto* sum = std::get_if<metrics_sdk::SumPointData>(&point);
            if (sum != nullptr) {
                total += std::get<int64_t>(sum->value_);
            }
        }
        return total;
    }

    std::shared_ptr<memory::SimpleAggregateInMemoryMetricData> metric_data_;
};

void expectRemote(const ProjectedDetections& geometry, size_t index, size_t k) {
    ASSERT_TRUE(geometry.has_geometry[index]);
    const auto& object = geometry.objects[index];
    EXPECT_DOUBLE_EQ(object.x, 10.0 + static_cast<double>(k));
    EXPECT_DOUBLE_EQ(object.y, 20.0 + static_cast<double>(k));
    EXPECT_DOUBLE_EQ(object.z, 0.0) << "centre z lowered by half the height";
    EXPECT_DOUBLE_EQ(object.length, 0.5);
    EXPECT_DOUBLE_EQ(object.width, 0.6);
    EXPECT_DOUBLE_EQ(object.height, kHeight);
    EXPECT_TRUE(object.zMeasured);
    ASSERT_TRUE(object.measurementNoiseCov.has_value());
    const auto r = denseR();
    for (size_t i = 0; i < r.size(); ++i) {
        EXPECT_EQ(object.measurementNoiseCov->val[i], r[i])
            << "R(" << i / 7 << ", " << i % 7 << ")";
    }
}

void expectLocal(const ProjectedDetections& geometry, size_t index) {
    ASSERT_TRUE(geometry.has_geometry[index]);
    const auto& object = geometry.objects[index];
    EXPECT_DOUBLE_EQ(object.x, 100.0 + static_cast<double>(index));
    EXPECT_FALSE(object.zMeasured);
    EXPECT_FALSE(object.measurementNoiseCov.has_value());
}

TEST_F(RemoteProjectorTest, AppliesRemoteMeasurementAndKeepsLocalOrientation) {
    auto client = std::make_shared<FakeClient>();
    auto projector = makeProjector(client, ConditioningMode::FrustumOnly);
    const std::vector<DetectionBatch> batches = {
        makeBatch("cam-1", {pixelDetection(), pixelDetection()})};

    auto projected = projector.project(batches);

    ASSERT_EQ(projected.size(), 1u);
    ASSERT_TRUE(projected[0].has_value());
    expectRemote(*projected[0], 0, 0);
    expectRemote(*projected[0], 1, 1);
    EXPECT_DOUBLE_EQ(projected[0]->objects[0].yaw, kLocalYaw);
    EXPECT_EQ(projected[0]->objects[0].attributes.at("has_orientation"), "1");

    ASSERT_EQ(client->calls, 1);
    EXPECT_EQ(client->last_scene_id, "scene-uid");
    EXPECT_EQ(client->last_category, "person");
    EXPECT_EQ(client->last_mode, ConditioningMode::FrustumOnly);
    ASSERT_EQ(client->last_frames.size(), 1u);
    EXPECT_EQ(client->last_frames[0].camera_id, "cam-1");
    EXPECT_EQ(client->last_frames[0].timestamp, batches[0].timestamp);
    EXPECT_EQ(client->last_frames[0].boxes.size(), 2u);
    EXPECT_EQ(failedCalls("UNAVAILABLE"), 0);
}

TEST_F(RemoteProjectorTest, SendsOnlyValidPixelBoxesAndMapsRepliesBack) {
    auto client = std::make_shared<FakeClient>();
    auto projector = makeProjector(client);
    auto nan_box = pixelDetection();
    nan_box.bounding_box_px.x = std::numeric_limits<float>::quiet_NaN();
    auto negative_box = pixelDetection();
    negative_box.bounding_box_px.width = -1.0f;
    const std::vector<DetectionBatch> batches = {
        makeBatch("cam-1", {translationDetection(), pixelDetection(), nan_box, negative_box,
                            pixelDetection()})};

    auto projected = projector.project(batches);

    ASSERT_EQ(client->last_frames.size(), 1u);
    ASSERT_EQ(client->last_frames[0].boxes.size(), 2u);
    expectLocal(*projected[0], 0);
    expectRemote(*projected[0], 1, 0);
    expectLocal(*projected[0], 2);
    expectLocal(*projected[0], 3);
    expectRemote(*projected[0], 4, 1);
}

TEST_F(RemoteProjectorTest, RemoteMeasurementGivesGeometryWhereLocalHasNone) {
    auto client = std::make_shared<FakeClient>();
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection(99)})};

    auto projected = projector.project(batches);

    expectRemote(*projected[0], 0, 0);
    EXPECT_DOUBLE_EQ(projected[0]->objects[0].yaw, 0.0);
    EXPECT_FALSE(projected[0]->objects[0].attributes.contains("has_orientation"));
}

TEST_F(RemoteProjectorTest, SkipsCallWithoutSendableDetections) {
    auto client = std::make_shared<FakeClient>();
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {makeBatch("unknown", {pixelDetection()}),
                                                 makeBatch("cam-1", {translationDetection()}),
                                                 makeBatch("cam-2", {})};

    auto projected = projector.project(batches);

    EXPECT_EQ(client->calls, 0);
    ASSERT_EQ(projected.size(), 3u);
    EXPECT_FALSE(projected[0].has_value()) << "unknown camera stays unprojected";
    expectLocal(*projected[1], 0);
}

TEST_F(RemoteProjectorTest, SendsFramesOfAllProjectableCamerasInOneCall) {
    auto client = std::make_shared<FakeClient>();
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection()}),
                                                 makeBatch("unknown", {pixelDetection()}),
                                                 makeBatch("cam-2", {pixelDetection()})};

    auto projected = projector.project(batches);

    ASSERT_EQ(client->calls, 1);
    ASSERT_EQ(client->last_frames.size(), 2u);
    EXPECT_EQ(client->last_frames[0].camera_id, "cam-1");
    EXPECT_EQ(client->last_frames[1].camera_id, "cam-2");
    expectRemote(*projected[0], 0, 0);
    EXPECT_FALSE(projected[1].has_value());
    expectRemote(*projected[2], 0, 0);
}

TEST_F(RemoteProjectorTest, FailedCallKeepsLocalProjectionAndIsCounted) {
    auto client = std::make_shared<FakeClient>([](const ProjectionFrame& frame) {
        return frame.camera_id == "cam-1" ? ProjectionReply{"UNAVAILABLE", {}} : goodReply(frame);
    });
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection()}),
                                                 makeBatch("cam-2", {pixelDetection()})};

    for (int i = 0; i < 3; ++i) {
        auto projected = projector.project(batches);
        expectLocal(*projected[0], 0);
        expectRemote(*projected[1], 0, 0);
    }
    EXPECT_EQ(failedCalls("UNAVAILABLE"), 3) << "every failure counts, also with muted warnings";
}

TEST_F(RemoteProjectorTest, ClientExceptionKeepsLocalProjection) {
    auto client = std::make_shared<FakeClient>();
    client->throw_error = true;
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection()}),
                                                 makeBatch("cam-2", {pixelDetection()})};

    std::vector<std::optional<ProjectedDetections>> projected;
    ASSERT_NO_THROW(projected = projector.project(batches));
    expectLocal(*projected[0], 0);
    expectLocal(*projected[1], 0);
    EXPECT_EQ(failedCalls("client_error"), 2);
}

TEST_F(RemoteProjectorTest, MissingReplyKeepsLocalProjection) {
    auto client = std::make_shared<FakeClient>();
    client->drop_last_reply = true;
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection()}),
                                                 makeBatch("cam-2", {pixelDetection()})};

    auto projected = projector.project(batches);

    expectLocal(*projected[0], 0);
    expectLocal(*projected[1], 0);
    EXPECT_EQ(failedCalls("invalid_response"), 2);
}

TEST_F(RemoteProjectorTest, MalformedReplyKeepsLocalProjectionForTheFrame) {
    // cam-1: one measurement for two detections; cam-2: detection ids out of order.
    auto client = std::make_shared<FakeClient>([](const ProjectionFrame& frame) {
        auto reply = goodReply(frame);
        if (frame.camera_id == "cam-1") {
            reply.measurements.pop_back();
        } else {
            std::swap(reply.measurements[0].detection_id, reply.measurements[1].detection_id);
        }
        return reply;
    });
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {
        makeBatch("cam-1", {pixelDetection(), pixelDetection()}),
        makeBatch("cam-2", {pixelDetection(), pixelDetection()})};

    auto projected = projector.project(batches);

    for (const auto& geometry : projected) {
        expectLocal(*geometry, 0);
        expectLocal(*geometry, 1);
    }
    EXPECT_EQ(failedCalls("invalid_response"), 2);
}

TEST_F(RemoteProjectorTest, UnobservableDepthKeepsLocalProjectionWithoutFailure) {
    auto client = std::make_shared<FakeClient>([](const ProjectionFrame& frame) {
        auto reply = goodReply(frame);
        reply.measurements[0] = RemoteMeasurement{"0", true, {}, {}};
        return reply;
    });
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {
        makeBatch("cam-1", {pixelDetection(), pixelDetection()})};

    auto projected = projector.project(batches);

    expectLocal(*projected[0], 0);
    expectRemote(*projected[0], 1, 1);
    EXPECT_EQ(failedCalls("invalid_measurement"), 0);
}

TEST_F(RemoteProjectorTest, InvalidMeasurementsKeepLocalProjection) {
    const auto nan = std::numeric_limits<double>::quiet_NaN();
    std::vector<std::function<void(RemoteMeasurement&)>> corruptions = {
        [](RemoteMeasurement& m) { m.mean.pop_back(); },
        [](RemoteMeasurement& m) { m.noise_covariance.pop_back(); },
        [nan](RemoteMeasurement& m) { m.mean[0] = nan; },
        [](RemoteMeasurement& m) { m.mean[5] = 0.0; },
        [](RemoteMeasurement& m) { m.mean[3] = -0.5; },
        [nan](RemoteMeasurement& m) { m.noise_covariance[1] = nan; },
        [](RemoteMeasurement& m) { m.noise_covariance[0] = -0.04; },
        [](RemoteMeasurement& m) { m.noise_covariance[16] = 0.0; },
        // Off-diagonal larger than the diagonal: symmetric but indefinite.
        [](RemoteMeasurement& m) { m.noise_covariance[1] = m.noise_covariance[7] = 1.0; },
        // No values: OK without a measurement, UNSPECIFIED or an unknown status.
        [](RemoteMeasurement& m) {
            m.mean.clear();
            m.noise_covariance.clear();
        },
    };
    const size_t n = corruptions.size();
    // Detection k gets corruption k; the last detection stays valid.
    auto client = std::make_shared<FakeClient>([&corruptions](const ProjectionFrame& frame) {
        auto reply = goodReply(frame);
        for (size_t k = 0; k < corruptions.size(); ++k) {
            corruptions[k](reply.measurements[k]);
        }
        return reply;
    });
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {
        makeBatch("cam-1", std::vector<Detection>(n + 1, pixelDetection()))};

    auto projected = projector.project(batches);

    for (size_t k = 0; k < n; ++k) {
        SCOPED_TRACE(k);
        expectLocal(*projected[0], k);
    }
    expectRemote(*projected[0], n, n);
    EXPECT_EQ(failedCalls("invalid_measurement"), 1) << "counted once per call";
}

TEST_F(RemoteProjectorTest, SymmetrizesSlightlyAsymmetricCovariance) {
    auto client = std::make_shared<FakeClient>([](const ProjectionFrame& frame) {
        auto reply = goodReply(frame);
        reply.measurements[0].noise_covariance[1] = 0.010;
        reply.measurements[0].noise_covariance[7] = 0.012;
        return reply;
    });
    auto projector = makeProjector(client);
    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection()})};

    auto projected = projector.project(batches);

    const auto& r = projected[0]->objects[0].measurementNoiseCov;
    ASSERT_TRUE(r.has_value());
    EXPECT_DOUBLE_EQ((*r)(0, 1), 0.011);
    EXPECT_DOUBLE_EQ((*r)(1, 0), 0.011);
    EXPECT_EQ((*r)(2, 5), -0.030) << "other cross terms unchanged";
    EXPECT_EQ((*r)(6, 3), 0.010);
}

TEST_F(RemoteProjectorTest, MismatchedLocalResultIsReturnedUnchanged) {
    class EmptyProjector final : public DetectionProjector {
    public:
        std::vector<std::optional<ProjectedDetections>>
        project(std::span<const DetectionBatch>) override {
            return {};
        }
    };
    auto client = std::make_shared<FakeClient>();
    RemoteProjector projector({"scene-uid", "person"}, std::make_unique<EmptyProjector>(), client,
                              ConditioningMode::Auto);
    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection()})};

    EXPECT_TRUE(projector.project(batches).empty());
    EXPECT_EQ(client->calls, 0);
}

TEST_F(RemoteProjectorTest, RejectsMissingDependencies) {
    EXPECT_THROW(RemoteProjector({"s", "c"}, nullptr, std::make_shared<FakeClient>(),
                                 ConditioningMode::Auto),
                 std::invalid_argument);
    EXPECT_THROW(RemoteProjector({"s", "c"}, std::make_unique<FakeLocalProjector>(), nullptr,
                                 ConditioningMode::Auto),
                 std::invalid_argument);
}

// ---------------------------------------------------------------------------------------------
// makeProjectorFactory
// ---------------------------------------------------------------------------------------------

ServiceConfig remoteConfig() {
    ServiceConfig config;
    config.tracking.experimental_remote_projection = true;
    config.tracking.remote_projection_mode = ConditioningMode::Full;
    config.infrastructure.remote_projection =
        RemoteProjectionConfig{.host = "projection", .port = 50051};
    return config;
}

class ProjectorFactoryTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("error"); }
    void TearDown() override { Logger::shutdown(); }

    ProjectionClientFactory connect = [this](const RemoteProjectionConfig& endpoint) {
        ++connects;
        connected_host = endpoint.host;
        return client;
    };
    std::shared_ptr<FakeClient> client = std::make_shared<FakeClient>();
    int connects = 0;
    std::string connected_host;
};

TEST_F(ProjectorFactoryTest, EnabledWithEndpointCreatesRemoteProjectors) {
    const auto factory = makeProjectorFactory(remoteConfig(), connect);

    ASSERT_TRUE(factory);
    EXPECT_EQ(connects, 1);
    EXPECT_EQ(connected_host, "projection");

    Camera camera;
    camera.uid = "cam-1";
    camera.intrinsics = {905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}};
    camera.extrinsics.translation = {0.0, 0.0, 3.0};
    camera.extrinsics.rotation = {-90.0, 0.0, 0.0};
    camera.extrinsics.scale = {1.0, 1.0, 1.0};
    auto projector = factory({"scene-uid", "person"}, {{"cam-1", camera}}, ObjectClassConfig{});
    ASSERT_NE(dynamic_cast<RemoteProjector*>(projector.get()), nullptr);

    const std::vector<DetectionBatch> batches = {makeBatch("cam-1", {pixelDetection()})};
    auto projected = projector->project(batches);
    EXPECT_EQ(client->calls, 1);
    EXPECT_EQ(client->last_mode, ConditioningMode::Full);
    expectRemote(*projected[0], 0, 0);
}

TEST_F(ProjectorFactoryTest, DisabledFlagUsesLocalProjection) {
    auto config = remoteConfig();
    config.tracking.experimental_remote_projection = false;

    EXPECT_FALSE(makeProjectorFactory(config, connect));
    EXPECT_EQ(connects, 0);
}

TEST_F(ProjectorFactoryTest, MissingEndpointUsesLocalProjection) {
    auto config = remoteConfig();
    config.infrastructure.remote_projection.reset();
    EXPECT_FALSE(makeProjectorFactory(config, connect));

    config = remoteConfig();
    config.infrastructure.remote_projection->host.clear();
    EXPECT_FALSE(makeProjectorFactory(config, connect));

    config = remoteConfig();
    config.infrastructure.remote_projection->port = 0;
    EXPECT_FALSE(makeProjectorFactory(config, connect));

    EXPECT_EQ(connects, 0);
}

TEST_F(ProjectorFactoryTest, TimeoutAboveChunkIntervalOnlyWarns) {
    auto config = remoteConfig();
    config.tracking.time_chunking_rate_fps = 30; // 33.3 ms chunk interval
    config.infrastructure.remote_projection->timeout_ms = 50;

    EXPECT_TRUE(makeProjectorFactory(config, connect));
    EXPECT_EQ(connects, 1);
}

TEST_F(ProjectorFactoryTest, ConnectFailureUsesLocalProjection) {
    const ProjectionClientFactory throwing =
        [](const RemoteProjectionConfig&) -> std::shared_ptr<ProjectionClient> {
        throw std::runtime_error("no CA");
    };
    EXPECT_FALSE(makeProjectorFactory(remoteConfig(), throwing));

    const ProjectionClientFactory null_client = [](const RemoteProjectionConfig&) {
        return std::shared_ptr<ProjectionClient>{};
    };
    EXPECT_FALSE(makeProjectorFactory(remoteConfig(), null_client));
}

} // namespace
} // namespace tracker
