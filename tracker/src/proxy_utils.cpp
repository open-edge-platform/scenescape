// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "proxy_utils.hpp"
#include "logger.hpp"

#include <cstdlib>

namespace tracker {

namespace {

/**
 * @brief Check if an environment variable is set but empty.
 *
 * @param name The environment variable name.
 * @return true if the variable is set and its value is an empty string.
 */
bool isEnvVarEmpty(const char* name) {
    const char* value = std::getenv(name);
    return value != nullptr && value[0] == '\0';
}

/**
 * @brief Unset an environment variable if it exists and is empty.
 *
 * Paho MQTT library has a bug where it attempts to use proxy settings even
 * when the proxy environment variables are set to empty strings, causing
 * connection failures. This function clears such variables.
 *
 * @param name The environment variable name.
 * @return true if the variable was unset.
 */
bool unsetIfEmpty(const char* name) {
    if (isEnvVarEmpty(name)) {
        unsetenv(name);
        return true;
    }
    return false;
}

} // namespace

void clearEmptyProxyEnvVars() {
    bool cleared_any = false;
    cleared_any |= unsetIfEmpty("http_proxy");
    cleared_any |= unsetIfEmpty("HTTP_PROXY");
    cleared_any |= unsetIfEmpty("https_proxy");
    cleared_any |= unsetIfEmpty("HTTPS_PROXY");
    cleared_any |= unsetIfEmpty("no_proxy");
    cleared_any |= unsetIfEmpty("NO_PROXY");

    if (cleared_any) {
        LOG_DEBUG("Cleared empty proxy environment variables.");
    }
}

} // namespace tracker
