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
    if (!http_get) {
        return 1; // Invalid http_get function
    }

    if (endpoint.empty()) {
        return 1; // Invalid endpoint
    }

    if (port < 1 || port > 65535) {
        return 1; // Invalid port range
    }

    // Normalize endpoint to ensure it starts with /
    std::string normalized_endpoint = endpoint;
    if (!normalized_endpoint.empty() && normalized_endpoint[0] != '/') {
        normalized_endpoint = "/" + normalized_endpoint;
    }

    httplib::Result response = http_get(normalized_endpoint, port);

    return (response && response->status == 200) ? 0 : 1;
}

} // namespace tracker
