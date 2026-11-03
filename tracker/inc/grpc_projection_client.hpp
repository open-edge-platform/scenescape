// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <memory>

#include "remote_projection_config.hpp"
#include "remote_projector.hpp"

namespace grpc {
class Channel;
}

namespace tracker {

/**
 * @brief gRPC ProjectionClient: one ProjectDetections call per frame, all frames of a
 *        projectFrames() call in flight together under a deadline of `timeout`.
 *
 * Failed calls are reported with their gRPC status name, for example DEADLINE_EXCEEDED or
 * UNAVAILABLE. Thread-safe.
 */
std::shared_ptr<ProjectionClient> makeGrpcProjectionClient(std::shared_ptr<grpc::Channel> channel,
                                                           std::chrono::milliseconds timeout);

/**
 * @brief Channel to the configured endpoint: TLS verified with ca_cert_path (or the system
 *        roots), plaintext when insecure. HTTP proxies are not used. Connects lazily.
 * @throws std::runtime_error if ca_cert_path cannot be read
 */
std::shared_ptr<grpc::Channel> makeProjectionChannel(const RemoteProjectionConfig& config);

/// makeGrpcProjectionClient() over makeProjectionChannel(), with the configured timeout.
std::shared_ptr<ProjectionClient> connectProjectionService(const RemoteProjectionConfig& config);

} // namespace tracker
