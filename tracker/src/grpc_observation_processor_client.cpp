// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "grpc_observation_processor_client.hpp"

#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <grpcpp/grpcpp.h>

#include "observation_processor.grpc.pb.h"

namespace tracker {

namespace {

namespace pb = scenescape::observation_processor::v1;

/// Name of a failed call's status code.
std::string statusName(grpc::StatusCode code) {
    switch (code) {
        case grpc::StatusCode::CANCELLED:
            return "CANCELLED";
        case grpc::StatusCode::INVALID_ARGUMENT:
            return "INVALID_ARGUMENT";
        case grpc::StatusCode::DEADLINE_EXCEEDED:
            return "DEADLINE_EXCEEDED";
        case grpc::StatusCode::NOT_FOUND:
            return "NOT_FOUND";
        case grpc::StatusCode::ALREADY_EXISTS:
            return "ALREADY_EXISTS";
        case grpc::StatusCode::PERMISSION_DENIED:
            return "PERMISSION_DENIED";
        case grpc::StatusCode::UNAUTHENTICATED:
            return "UNAUTHENTICATED";
        case grpc::StatusCode::RESOURCE_EXHAUSTED:
            return "RESOURCE_EXHAUSTED";
        case grpc::StatusCode::FAILED_PRECONDITION:
            return "FAILED_PRECONDITION";
        case grpc::StatusCode::ABORTED:
            return "ABORTED";
        case grpc::StatusCode::OUT_OF_RANGE:
            return "OUT_OF_RANGE";
        case grpc::StatusCode::UNIMPLEMENTED:
            return "UNIMPLEMENTED";
        case grpc::StatusCode::INTERNAL:
            return "INTERNAL";
        case grpc::StatusCode::UNAVAILABLE:
            return "UNAVAILABLE";
        case grpc::StatusCode::DATA_LOSS:
            return "DATA_LOSS";
        default:
            return "UNKNOWN";
    }
}

pb::ConditioningMode toProto(ConditioningMode mode) {
    switch (mode) {
        case ConditioningMode::Full:
            return pb::CONDITIONING_MODE_FULL;
        case ConditioningMode::FrustumOnly:
            return pb::CONDITIONING_MODE_FRUSTUM_ONLY;
        case ConditioningMode::Auto:
            break;
    }
    return pb::CONDITIONING_MODE_AUTO;
}

void fillRequest(pb::ProcessDetectionsRequest& request, const std::string& scene_id,
                 const std::string& category, ConditioningMode mode,
                 const ObservationProcessorFrame& frame) {
    request.set_scene_id(scene_id);
    request.set_camera_id(frame.camera_id);
    const auto since_epoch = frame.timestamp.time_since_epoch();
    const auto seconds = std::chrono::floor<std::chrono::seconds>(since_epoch);
    const auto nanos = std::chrono::duration_cast<std::chrono::nanoseconds>(since_epoch - seconds);
    request.mutable_timestamp()->set_seconds(seconds.count());
    request.mutable_timestamp()->set_nanos(static_cast<int32_t>(nanos.count()));
    request.set_mode(toProto(mode));

    auto* detections = request.mutable_detections();
    detections->Reserve(static_cast<int>(frame.boxes.size()));
    for (size_t i = 0; i < frame.boxes.size(); ++i) {
        const auto& box = frame.boxes[i];
        auto* detection = detections->Add();
        detection->set_detection_id(std::to_string(i));
        detection->set_category(category);
        auto* pixels = detection->mutable_bounding_box_px();
        pixels->set_x(box.x);
        pixels->set_y(box.y);
        pixels->set_width(box.width);
        pixels->set_height(box.height);
    }
}

ObservationProcessorReply toReply(const grpc::Status& status,
                                  const pb::ProcessDetectionsResponse& response) {
    ObservationProcessorReply reply;
    if (!status.ok()) {
        reply.error = statusName(status.error_code());
        return reply;
    }
    reply.measurements.reserve(static_cast<size_t>(response.measurements_size()));
    for (const auto& measurement : response.measurements()) {
        RemoteMeasurement out;
        out.detection_id = measurement.detection_id();
        out.unobservable = measurement.status() == pb::MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE;
        if (measurement.status() == pb::MEASUREMENT_STATUS_OK && measurement.has_measurement()) {
            const auto& values = measurement.measurement();
            out.mean.assign(values.mean().begin(), values.mean().end());
            out.noise_covariance.assign(values.noise_covariance().begin(),
                                        values.noise_covariance().end());
        }
        reply.measurements.push_back(std::move(out));
    }
    return reply;
}

class GrpcObservationProcessorClient final : public ObservationProcessorClient {
public:
    GrpcObservationProcessorClient(const std::shared_ptr<grpc::Channel>& channel,
                                   std::chrono::milliseconds timeout)
        : stub_(pb::ObservationProcessorService::NewStub(channel)), timeout_(timeout) {}

    std::vector<ObservationProcessorReply>
    processFrames(const std::string& scene_id, const std::string& category, ConditioningMode mode,
                  std::span<const ObservationProcessorFrame> frames) override {
        struct Call {
            grpc::ClientContext context;
            pb::ProcessDetectionsRequest request;
            pb::ProcessDetectionsResponse response;
            grpc::Status status;
            std::unique_ptr<grpc::ClientAsyncResponseReader<pb::ProcessDetectionsResponse>> reader;
        };

        const auto deadline = std::chrono::system_clock::now() + timeout_;
        grpc::CompletionQueue queue;
        std::vector<std::unique_ptr<Call>> calls;
        calls.reserve(frames.size());
        for (const auto& frame : frames) {
            auto& call = *calls.emplace_back(std::make_unique<Call>());
            call.context.set_deadline(deadline);
            fillRequest(call.request, scene_id, category, mode, frame);
            call.reader = stub_->AsyncProcessDetections(&call.context, call.request, &queue);
            call.reader->Finish(&call.response, &call.status, &call);
        }

        // The deadline completes every call.
        void* tag = nullptr;
        bool ok = false;
        for (size_t pending = calls.size(); pending > 0 && queue.Next(&tag, &ok); --pending) {}
        queue.Shutdown();
        while (queue.Next(&tag, &ok)) {}

        std::vector<ObservationProcessorReply> replies;
        replies.reserve(calls.size());
        for (const auto& call : calls) {
            replies.push_back(toReply(call->status, call->response));
        }
        return replies;
    }

private:
    std::unique_ptr<pb::ObservationProcessorService::Stub> stub_;
    std::chrono::milliseconds timeout_;
};

std::string readFile(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        throw std::runtime_error("Cannot read observation processor CA certificate: " + path);
    }
    std::ostringstream content;
    content << file.rdbuf();
    return content.str();
}

} // namespace

std::shared_ptr<ObservationProcessorClient>
makeGrpcObservationProcessorClient(std::shared_ptr<grpc::Channel> channel,
                                   std::chrono::milliseconds timeout) {
    if (!channel) {
        throw std::invalid_argument("Observation processor client requires a channel");
    }
    return std::make_shared<GrpcObservationProcessorClient>(channel, timeout);
}

std::shared_ptr<grpc::Channel>
makeObservationProcessorChannel(const RemoteObservationProcessorConfig& config) {
    std::shared_ptr<grpc::ChannelCredentials> credentials;
    if (config.insecure) {
        credentials = grpc::InsecureChannelCredentials();
    } else {
        grpc::SslCredentialsOptions options;
        if (!config.ca_cert_path.empty()) {
            options.pem_root_certs = readFile(config.ca_cert_path);
        }
        credentials = grpc::SslCredentials(options);
    }
    grpc::ChannelArguments arguments;
    arguments.SetInt(GRPC_ARG_ENABLE_HTTP_PROXY, 0);
    return grpc::CreateCustomChannel(config.host + ":" + std::to_string(config.port), credentials,
                                     arguments);
}

std::shared_ptr<ObservationProcessorClient>
connectObservationProcessorService(const RemoteObservationProcessorConfig& config) {
    auto channel = makeObservationProcessorChannel(config);
    // Start connecting now, without blocking, so that the first chunk does not spend its
    // deadline on name resolution and the handshake.
    channel->GetState(true);
    return makeGrpcObservationProcessorClient(std::move(channel),
                                              std::chrono::milliseconds(config.timeout_ms));
}

} // namespace tracker
