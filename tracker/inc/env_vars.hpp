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

/// Environment variable for overriding MQTT broker host
constexpr const char* MQTT_HOST = "TRACKER_MQTT_HOST";

/// Environment variable for overriding MQTT broker port (1-65535)
constexpr const char* MQTT_PORT = "TRACKER_MQTT_PORT";

/// Environment variable for overriding MQTT insecure mode (true/false)
constexpr const char* MQTT_INSECURE = "TRACKER_MQTT_INSECURE";

/// Environment variable for overriding SSL CA certificate path
constexpr const char* SSL_CA_CERT = "TRACKER_SSL_CA_CERT";

/// Environment variable for overriding SSL client certificate path
constexpr const char* SSL_CLIENT_CERT = "TRACKER_SSL_CLIENT_CERT";

/// Environment variable for overriding SSL client key path
constexpr const char* SSL_CLIENT_KEY = "TRACKER_SSL_CLIENT_KEY";

/// Environment variable for overriding SSL server verification (true/false)
constexpr const char* SSL_VERIFY_SERVER = "TRACKER_SSL_VERIFY_SERVER";

} // namespace tracker::env
