// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <httplib.h>
#include <iostream>
#include <string>

namespace tracker {

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
 * @param port Port number to connect to
 * @return Exit code: 0 for healthy, 1 for unhealthy
 */
int run_healthcheck_command(const std::string& endpoint, int port) {
    // Normalize endpoint to ensure it starts with /
    std::string normalized_endpoint = endpoint;
    if (!normalized_endpoint.empty() && normalized_endpoint[0] != '/') {
        normalized_endpoint = "/" + normalized_endpoint;
    }

    // Create HTTP client
    httplib::Client client("localhost", port);
    client.set_connection_timeout(1, 0); // 1 second timeout

    // Make GET request
    auto response = client.Get(normalized_endpoint.c_str());

    // Check response
    if (response && response->status == 200) {
        return 0; // Success
    }

    // Failure (unreachable or unhealthy)
    return 1;
}

} // namespace tracker
