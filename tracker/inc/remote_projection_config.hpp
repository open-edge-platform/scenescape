// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <stdexcept>
#include <string>
#include <string_view>

namespace tracker {

/**
 * @brief Conditioning requested from the remote projection service
 *        (scenescape.projection.v1.ConditioningMode).
 */
enum class ConditioningMode {
    Auto,        ///< Full when the scene has a mesh, frustum only otherwise
    Full,        ///< Frustum Gaussian, then amodal conditioning against the scene mesh
    FrustumOnly, ///< Frustum Gaussian only
};

/// @throws std::runtime_error for a value other than auto, full or frustum_only
inline ConditioningMode parseConditioningMode(std::string_view value) {
    if (value == "auto") {
        return ConditioningMode::Auto;
    }
    if (value == "full") {
        return ConditioningMode::Full;
    }
    if (value == "frustum_only") {
        return ConditioningMode::FrustumOnly;
    }
    throw std::runtime_error("Invalid remote projection mode: " + std::string(value) +
                             " (must be auto|full|frustum_only)");
}

inline std::string_view toString(ConditioningMode mode) {
    switch (mode) {
        case ConditioningMode::Full:
            return "full";
        case ConditioningMode::FrustumOnly:
            return "frustum_only";
        case ConditioningMode::Auto:
            break;
    }
    return "auto";
}

constexpr int kDefaultRemoteProjectionTimeoutMs = 50;

/**
 * @brief Remote projection service connection (experimental).
 *
 * Used only when tracking.experimental_remote_projection is set and the endpoint is defined.
 */
struct RemoteProjectionConfig {
    std::string host;
    int port = 0;
    bool insecure = false;    ///< Plaintext channel instead of TLS (development only)
    std::string ca_cert_path; ///< PEM CA certificates for TLS; empty uses the system roots
    int timeout_ms = kDefaultRemoteProjectionTimeoutMs; ///< Deadline for the calls of one chunk

    /// True when host and port are set.
    [[nodiscard]] bool hasEndpoint() const { return !host.empty() && port > 0; }
};

} // namespace tracker
