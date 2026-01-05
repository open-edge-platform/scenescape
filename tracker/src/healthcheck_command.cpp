// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck_command.hpp"

#include <httplib.h>
#include <iostream>
#include <string>

namespace tracker {

httplib::Result make_http_request(const std::string& endpoint, int port) {
    httplib::Client client("localhost", port);
    client.set_connection_timeout(1, 0); // 1 second timeout
    return client.Get(endpoint.c_str());
}

int run_healthcheck_command(const std::string& endpoint, int port, HttpGetFunction http_get) {
    // Normalize endpoint to ensure it starts with /
    std::string normalized_endpoint = endpoint;
    if (!normalized_endpoint.empty() && normalized_endpoint[0] != '/') {
        normalized_endpoint = "/" + normalized_endpoint;
    }

    // Use provided HTTP GET function or default implementation
    httplib::Result response;
    if (http_get) {
        response = http_get(normalized_endpoint);
    } else {
        response = make_http_request(normalized_endpoint, port);
    }

    // Check response
    if (response && response->status == 200) {
        return 0; // Success
    }

    // Failure (unreachable or unhealthy)
    return 1;
}

} // namespace tracker
