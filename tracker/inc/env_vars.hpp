// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

// -----------------------------------------------------------------------------
// Environment variable names for runtime configuration overrides.
//
// These constants provide a single source of truth for environment variable
// names used to override configuration file values at runtime.
// -----------------------------------------------------------------------------

namespace tracker::env {

/// Environment variable for overriding log level (trace/debug/info/warn/error)
constexpr const char* LOG_LEVEL = "TRACKER_LOG_LEVEL";

/// Environment variable for overriding healthcheck server port (1024-65535)
constexpr const char* HEALTHCHECK_PORT = "TRACKER_HEALTHCHECK_PORT";

} // namespace tracker::env
