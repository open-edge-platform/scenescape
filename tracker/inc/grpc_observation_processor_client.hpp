// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <memory>

#include "remote_observation_processor.hpp"
#include "remote_observation_processor_config.hpp"

namespace grpc {
class Channel;
}

namespace tracker {

/**
 * @brief gRPC ObservationProcessorClient: one ProcessDetections call per frame, all frames of a
 *        processFrames() call in flight together under a deadline of `timeout`.
 *
 * Failed calls are reported with their gRPC status name, for example DEADLINE_EXCEEDED or
 * UNAVAILABLE. Thread-safe.
 */
std::shared_ptr<ObservationProcessorClient>
makeGrpcObservationProcessorClient(std::shared_ptr<grpc::Channel> channel,
                                   std::chrono::milliseconds timeout);

/**
 * @brief Channel to the configured endpoint: TLS verified with ca_cert_path (or the system
 *        roots), plaintext when insecure. HTTP proxies are not used. Connects lazily.
 * @throws std::runtime_error if ca_cert_path cannot be read
 */
std::shared_ptr<grpc::Channel>
makeObservationProcessorChannel(const RemoteObservationProcessorConfig& config);

/// makeGrpcObservationProcessorClient() over makeObservationProcessorChannel(), with the configured
/// timeout. The channel starts connecting in the background, so the first call does not wait for
/// it.
std::shared_ptr<ObservationProcessorClient>
connectObservationProcessorService(const RemoteObservationProcessorConfig& config);

} // namespace tracker
