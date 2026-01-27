// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

// -----------------------------------------------------------------------------
// Service version metadata (compile-time constants)
//
// All values are injected by CMake via compile definitions:
//   - TRACKER_SERVICE_NAME
//   - TRACKER_SERVICE_VERSION
//   - TRACKER_GIT_COMMIT
//
// Fallback defaults are provided for IDE/local development without CMake.
// -----------------------------------------------------------------------------

#ifndef TRACKER_SERVICE_NAME
    #define TRACKER_SERVICE_NAME "tracker"
#endif

#ifndef TRACKER_SERVICE_VERSION
    #define TRACKER_SERVICE_VERSION "dev"
#endif

#ifndef TRACKER_GIT_COMMIT
    #define TRACKER_GIT_COMMIT "unknown"
#endif

namespace tracker {

constexpr const char* SERVICE_NAME = TRACKER_SERVICE_NAME;
constexpr const char* SERVICE_VERSION = TRACKER_SERVICE_VERSION;
constexpr const char* GIT_COMMIT = TRACKER_GIT_COMMIT;

} // namespace tracker
