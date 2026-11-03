// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "grpc_projection_client.hpp"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <grpcpp/grpcpp.h>
#include <gtest/gtest.h>

#include "projection/v1/projection.grpc.pb.h"

namespace tracker {
namespace {

namespace pb = scenescape::projection::v1;

// Measurement x is the detection index, y is the request's camera index ("cam-<y>").
class FakeProjectionService final : public pb::ProjectionService::Service {
public:
    grpc::Status ProjectDetections(grpc::ServerContext*,
                                   const pb::ProjectDetectionsRequest* request,
                                   pb::ProjectDetectionsResponse* response) override {
        {
            std::lock_guard lock(mutex);
            requests.push_back(*request);
        }
        if (delay.count() > 0) {
            std::this_thread::sleep_for(delay);
        }
        if (request->camera_id() == "uncalibrated") {
            return {grpc::StatusCode::FAILED_PRECONDITION, "camera is not calibrated"};
        }
        if (request->camera_id().starts_with("status-")) {
            return {static_cast<grpc::StatusCode>(std::stoi(request->camera_id().substr(7))), ""};
        }
        response->set_scene_id(request->scene_id());
        response->set_camera_id(request->camera_id());
        *response->mutable_timestamp() = request->timestamp();
        response->set_mode(pb::CONDITIONING_MODE_FRUSTUM_ONLY);
        const double camera = std::stod(request->camera_id().substr(4));
        for (int i = 0; i < request->detections_size(); ++i) {
            const auto& detection = request->detections(i);
            auto* out = response->add_measurements();
            out->set_detection_id(detection.detection_id());
            if (detection.bounding_box_px().width() == 0.0) {
                out->set_status(pb::MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE);
                continue;
            }
            // Malformed entries selected by the box height: 1 = OK without a measurement,
            // 2 = UNSPECIFIED with a measurement, 3 = an unknown status with a measurement.
            const double malformed = detection.bounding_box_px().height();
            if (malformed == 1.0) {
                out->set_status(pb::MEASUREMENT_STATUS_OK);
                continue;
            }
            out->set_status(malformed == 2.0   ? pb::MEASUREMENT_STATUS_UNSPECIFIED
                            : malformed == 3.0 ? static_cast<pb::MeasurementStatus>(7)
                                               : pb::MEASUREMENT_STATUS_OK);
            auto* measurement = out->mutable_measurement();
            for (double value : {static_cast<double>(i), camera, 0.85, 0.5, 0.5, 1.7, 0.0}) {
                measurement->add_mean(value);
            }
            // Distinct off-diagonal values show that all 49 entries arrive in row-major order.
            for (int k = 0; k < 49; ++k) {
                measurement->add_noise_covariance(k % 8 == 0 ? 0.1 : 0.001 * k);
            }
            measurement->set_z_measured(true);
        }
        return grpc::Status::OK;
    }

    std::mutex mutex;
    std::vector<pb::ProjectDetectionsRequest> requests;
    std::chrono::milliseconds delay{0};
};

class GrpcProjectionClientTest : public ::testing::Test {
protected:
    void SetUp() override {
        grpc::ServerBuilder builder;
        builder.RegisterService(&service_);
        server_ = builder.BuildAndStart();
        ASSERT_NE(server_, nullptr);
        channel_ = server_->InProcessChannel(grpc::ChannelArguments{});
    }

    void TearDown() override { server_->Shutdown(); }

    static ProjectionFrame frame(const std::string& camera_id, size_t boxes) {
        ProjectionFrame result{
            camera_id,
            std::chrono::system_clock::time_point(std::chrono::seconds(1'700'000'000) +
                                                  std::chrono::nanoseconds(250'000'000)),
            {}};
        for (size_t i = 0; i < boxes; ++i) {
            result.boxes.emplace_back(10.0f * static_cast<float>(i), 20.0f, 30.0f, 60.0f);
        }
        return result;
    }

    FakeProjectionService service_;
    std::unique_ptr<grpc::Server> server_;
    std::shared_ptr<grpc::Channel> channel_;
};

TEST_F(GrpcProjectionClientTest, SendsRequestAndConvertsReply) {
    auto client = makeGrpcProjectionClient(channel_, std::chrono::milliseconds(2000));
    auto unobservable = frame("cam-3", 2);
    unobservable.boxes[1].width = 0.0f;

    const std::vector<ProjectionFrame> frames = {unobservable};
    const auto replies =
        client->projectFrames("scene-uid", "person", ConditioningMode::Full, frames);

    ASSERT_EQ(service_.requests.size(), 1u);
    const auto& request = service_.requests[0];
    EXPECT_EQ(request.scene_id(), "scene-uid");
    EXPECT_EQ(request.camera_id(), "cam-3");
    EXPECT_EQ(request.timestamp().seconds(), 1'700'000'000);
    EXPECT_EQ(request.timestamp().nanos(), 250'000'000);
    EXPECT_EQ(request.mode(), pb::CONDITIONING_MODE_FULL);
    EXPECT_FALSE(request.include_diagnostics());
    ASSERT_EQ(request.detections_size(), 2);
    EXPECT_EQ(request.detections(1).detection_id(), "1");
    EXPECT_EQ(request.detections(1).category(), "person");
    EXPECT_DOUBLE_EQ(request.detections(1).bounding_box_px().x(), 10.0);
    EXPECT_DOUBLE_EQ(request.detections(1).bounding_box_px().y(), 20.0);
    EXPECT_DOUBLE_EQ(request.detections(1).bounding_box_px().height(), 60.0);
    EXPECT_FALSE(request.detections(1).has_axis_aware_sizing());
    EXPECT_FALSE(request.detections(1).has_project_to_map());

    ASSERT_EQ(replies.size(), 1u);
    ASSERT_TRUE(replies[0].ok());
    ASSERT_EQ(replies[0].measurements.size(), 2u);
    const auto& measurement = replies[0].measurements[0];
    EXPECT_EQ(measurement.detection_id, "0");
    EXPECT_FALSE(measurement.unobservable);
    ASSERT_EQ(measurement.mean.size(), 7u);
    EXPECT_DOUBLE_EQ(measurement.mean[1], 3.0);
    EXPECT_DOUBLE_EQ(measurement.mean[2], 0.85);
    ASSERT_EQ(measurement.noise_covariance.size(), 49u);
    for (size_t k = 0; k < 49; ++k) {
        EXPECT_EQ(measurement.noise_covariance[k], k % 8 == 0 ? 0.1 : 0.001 * static_cast<int>(k))
            << "R entry " << k;
    }
    EXPECT_EQ(replies[0].measurements[1].detection_id, "1");
    EXPECT_TRUE(replies[0].measurements[1].unobservable);
    EXPECT_TRUE(replies[0].measurements[1].mean.empty());
}

TEST_F(GrpcProjectionClientTest, MalformedStatusesAreNotUnobservableAndHaveNoValues) {
    auto client = makeGrpcProjectionClient(channel_, std::chrono::milliseconds(2000));
    auto malformed = frame("cam-1", 3);
    for (size_t k = 0; k < 3; ++k) {
        malformed.boxes[k].height = static_cast<float>(k + 1);
    }

    const std::vector<ProjectionFrame> frames = {malformed};
    const auto replies =
        client->projectFrames("scene-uid", "person", ConditioningMode::Auto, frames);

    ASSERT_EQ(replies.size(), 1u);
    ASSERT_TRUE(replies[0].ok());
    ASSERT_EQ(replies[0].measurements.size(), 3u);
    for (const auto& measurement : replies[0].measurements) {
        SCOPED_TRACE(measurement.detection_id);
        EXPECT_FALSE(measurement.unobservable) << "validated, so counted as invalid_measurement";
        EXPECT_TRUE(measurement.mean.empty());
        EXPECT_TRUE(measurement.noise_covariance.empty());
    }
}

TEST_F(GrpcProjectionClientTest, MapsEveryConditioningMode) {
    auto client = makeGrpcProjectionClient(channel_, std::chrono::milliseconds(2000));
    const std::vector<ProjectionFrame> frames = {frame("cam-1", 1)};
    for (auto mode :
         {ConditioningMode::Auto, ConditioningMode::Full, ConditioningMode::FrustumOnly}) {
        client->projectFrames("scene-uid", "person", mode, frames);
    }
    ASSERT_EQ(service_.requests.size(), 3u);
    EXPECT_EQ(service_.requests[0].mode(), pb::CONDITIONING_MODE_AUTO);
    EXPECT_EQ(service_.requests[1].mode(), pb::CONDITIONING_MODE_FULL);
    EXPECT_EQ(service_.requests[2].mode(), pb::CONDITIONING_MODE_FRUSTUM_ONLY);
}

TEST_F(GrpcProjectionClientTest, RepliesFollowFrameOrderAndCarryPerFrameErrors) {
    auto client = makeGrpcProjectionClient(channel_, std::chrono::milliseconds(2000));
    const std::vector<ProjectionFrame> frames = {frame("cam-1", 1), frame("uncalibrated", 1),
                                                 frame("cam-2", 3)};

    const auto replies =
        client->projectFrames("scene-uid", "person", ConditioningMode::Auto, frames);

    ASSERT_EQ(replies.size(), 3u);
    ASSERT_TRUE(replies[0].ok());
    EXPECT_DOUBLE_EQ(replies[0].measurements[0].mean[1], 1.0);
    EXPECT_EQ(replies[1].error, "FAILED_PRECONDITION");
    EXPECT_TRUE(replies[1].measurements.empty());
    ASSERT_TRUE(replies[2].ok());
    ASSERT_EQ(replies[2].measurements.size(), 3u);
    EXPECT_DOUBLE_EQ(replies[2].measurements[2].mean[0], 2.0);
    EXPECT_DOUBLE_EQ(replies[2].measurements[2].mean[1], 2.0);
}

TEST_F(GrpcProjectionClientTest, ReportsGrpcStatusNames) {
    const std::vector<std::pair<grpc::StatusCode, std::string>> codes = {
        {grpc::StatusCode::CANCELLED, "CANCELLED"},
        {grpc::StatusCode::UNKNOWN, "UNKNOWN"},
        {grpc::StatusCode::INVALID_ARGUMENT, "INVALID_ARGUMENT"},
        {grpc::StatusCode::DEADLINE_EXCEEDED, "DEADLINE_EXCEEDED"},
        {grpc::StatusCode::NOT_FOUND, "NOT_FOUND"},
        {grpc::StatusCode::ALREADY_EXISTS, "ALREADY_EXISTS"},
        {grpc::StatusCode::PERMISSION_DENIED, "PERMISSION_DENIED"},
        {grpc::StatusCode::RESOURCE_EXHAUSTED, "RESOURCE_EXHAUSTED"},
        {grpc::StatusCode::FAILED_PRECONDITION, "FAILED_PRECONDITION"},
        {grpc::StatusCode::ABORTED, "ABORTED"},
        {grpc::StatusCode::OUT_OF_RANGE, "OUT_OF_RANGE"},
        {grpc::StatusCode::UNIMPLEMENTED, "UNIMPLEMENTED"},
        {grpc::StatusCode::INTERNAL, "INTERNAL"},
        {grpc::StatusCode::UNAVAILABLE, "UNAVAILABLE"},
        {grpc::StatusCode::DATA_LOSS, "DATA_LOSS"},
        {grpc::StatusCode::UNAUTHENTICATED, "UNAUTHENTICATED"},
    };
    std::vector<ProjectionFrame> frames;
    for (const auto& [code, name] : codes) {
        frames.push_back(frame("status-" + std::to_string(static_cast<int>(code)), 1));
    }
    auto client = makeGrpcProjectionClient(channel_, std::chrono::milliseconds(2000));

    const auto replies =
        client->projectFrames("scene-uid", "person", ConditioningMode::Auto, frames);

    ASSERT_EQ(replies.size(), codes.size());
    for (size_t i = 0; i < codes.size(); ++i) {
        EXPECT_EQ(replies[i].error, codes[i].second);
        EXPECT_FALSE(replies[i].ok());
    }
}

TEST_F(GrpcProjectionClientTest, FramesShareOneDeadline) {
    service_.delay = std::chrono::milliseconds(300);
    auto client = makeGrpcProjectionClient(channel_, std::chrono::milliseconds(50));
    const std::vector<ProjectionFrame> frames = {frame("cam-1", 1), frame("cam-2", 1),
                                                 frame("cam-3", 1)};

    const auto start = std::chrono::steady_clock::now();
    const auto replies =
        client->projectFrames("scene-uid", "person", ConditioningMode::Auto, frames);
    const auto elapsed = std::chrono::steady_clock::now() - start;

    ASSERT_EQ(replies.size(), 3u);
    for (const auto& reply : replies) {
        EXPECT_EQ(reply.error, "DEADLINE_EXCEEDED");
    }
    EXPECT_LT(elapsed, std::chrono::milliseconds(250)) << "calls run concurrently";
}

TEST_F(GrpcProjectionClientTest, UnreachableServiceIsUnavailable) {
    // Plaintext to a closed local port: the connection is refused.
    RemoteProjectionConfig config{
        .host = "127.0.0.1", .port = 1, .insecure = true, .timeout_ms = 1000};
    auto client = connectProjectionService(config);
    const std::vector<ProjectionFrame> frames = {frame("cam-1", 1)};

    const auto replies =
        client->projectFrames("scene-uid", "person", ConditioningMode::Auto, frames);

    ASSERT_EQ(replies.size(), 1u);
    EXPECT_EQ(replies[0].error, "UNAVAILABLE");
}

TEST_F(GrpcProjectionClientTest, EmptyFrameListMakesNoCalls) {
    auto client = makeGrpcProjectionClient(channel_, std::chrono::milliseconds(50));
    EXPECT_TRUE(client->projectFrames("scene-uid", "person", ConditioningMode::Auto, {}).empty());
    EXPECT_TRUE(service_.requests.empty());
}

TEST(ProjectionChannelTest, BuildsTlsAndPlaintextChannels) {
    const auto ca_path = std::filesystem::temp_directory_path() / "tracker_projection_ca_test.pem";
    { std::ofstream(ca_path) << "-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n"; }
    RemoteProjectionConfig config{.host = "projection", .port = 50051};
    EXPECT_NE(makeProjectionChannel(config), nullptr) << "TLS with the system roots";
    config.ca_cert_path = ca_path.string();
    EXPECT_NE(makeProjectionChannel(config), nullptr) << "TLS with a CA file";
    config.insecure = true;
    config.ca_cert_path = "/nonexistent/ca.pem";
    EXPECT_NE(makeProjectionChannel(config), nullptr) << "plaintext ignores the CA path";
    std::filesystem::remove(ca_path);
}

TEST(ProjectionChannelTest, UnreadableCaCertificateThrows) {
    RemoteProjectionConfig config{
        .host = "projection", .port = 50051, .ca_cert_path = "/nonexistent/ca.pem"};
    EXPECT_THROW(makeProjectionChannel(config), std::runtime_error);
    EXPECT_THROW(connectProjectionService(config), std::runtime_error);
}

TEST(ProjectionChannelTest, ClientRequiresChannel) {
    EXPECT_THROW(makeGrpcProjectionClient(nullptr, std::chrono::milliseconds(50)),
                 std::invalid_argument);
}

} // namespace
} // namespace tracker
