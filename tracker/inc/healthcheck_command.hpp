// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <functional>
#include <string>

#include <httplib.h>

namespace tracker {

/**
 * @brief Function type for making HTTP GET requests (for dependency injection/mocking).
 *
 * @param endpoint Health endpoint path (e.g., "/healthz", "/readyz")
 * @param port Port number to connect to (1-65535)
 * @return httplib::Result containing response or error
 */
using HttpGetFunction = std::function<httplib::Result(const std::string& endpoint, int port)>;

/**
 * @brief Default implementation of HttpGetFunction.
 *
 * Makes HTTP GET request to localhost healthcheck endpoint.
 * Used as the default http_get parameter in run_healthcheck_command.
 *
 * @param endpoint Health endpoint path (e.g., "/healthz", "/readyz")
 * @param port Port number to connect to (valid range: 1-65535)
 * @return httplib::Result containing response or error
 */
httplib::Result make_http_request(const std::string& endpoint, int port);

/**
 * @brief Run healthcheck command to query service health endpoint.
 *
 * Makes HTTP GET request to localhost:{port}/{endpoint} and returns:
 * - 0 if service returns 200 OK
 * - 1 if service is unhealthy or unreachable
 *
 * This function is designed for use as a Docker/Kubernetes healthcheck
 * command and intentionally skips logger initialization for minimal overhead.
 *
 * @param endpoint Health endpoint path (e.g., "/healthz", "/readyz")
 * @param port Port number to connect to (valid range: 1-65535)
 * @param http_get Custom HTTP GET function for dependency injection/testing
 * @return Exit code: 0 for healthy, 1 for unhealthy
 */
int run_healthcheck_command(const std::string& endpoint, int port,
                            HttpGetFunction http_get = make_http_request);

} // namespace tracker
