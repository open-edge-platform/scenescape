// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "proxy_utils.hpp"

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
    // Paho MQTT library cannot handle empty proxy environment variables.
    // If a proxy var is set to "" (empty string), Paho still tries to use it
    // and fails with connection errors. This commonly happens when:
    //   - Docker containers inherit empty proxy vars from the host
    //   - Compose files explicitly set proxy vars to empty to override host values
    //
    // Solution: detect empty proxy vars and unset them entirely.

    unsetIfEmpty("http_proxy");
    unsetIfEmpty("HTTP_PROXY");
    unsetIfEmpty("https_proxy");
    unsetIfEmpty("HTTPS_PROXY");
    unsetIfEmpty("no_proxy");
    unsetIfEmpty("NO_PROXY");
}

} // namespace tracker
