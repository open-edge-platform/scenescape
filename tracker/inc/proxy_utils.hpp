// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

namespace tracker {

/**
 * @brief Proxy environment variable utilities for Paho MQTT library workaround.
 *
 * The Paho MQTT C/C++ library has a bug where it attempts to use proxy settings
 * even when proxy environment variables are set to empty strings. This commonly
 * occurs when:
 *   - Docker containers inherit empty proxy vars from the host
 *   - Compose files explicitly set proxy vars to empty to override host values
 *
 * As a workaround, we detect empty proxy variables and unset them entirely
 * before Paho MQTT initialization.
 */

/**
 * @brief Clear proxy environment variables that are set but empty.
 *
 * Checks all proxy-related environment variables (http_proxy, HTTP_PROXY,
 * https_proxy, HTTPS_PROXY, no_proxy, NO_PROXY) and unsets any that are
 * set to an empty string.
 *
 * This works around a Paho MQTT bug where empty proxy vars cause connection
 * failures. Variables with actual proxy URLs are left intact.
 *
 * @note This modifies the process environment and affects all threads.
 * @note Must be called before any Paho MQTT library initialization.
 */
void clearEmptyProxyEnvVars();

} // namespace tracker
