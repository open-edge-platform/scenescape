// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "manager_rest_client.hpp"

#include "logger.hpp"

#include <stdexcept>

#include <httplib.h>
#include <rapidjson/document.h>

namespace tracker {

namespace {

/**
 * @brief Parse scheme, host, and port from a URL string.
 *
 * Supports http:// and https:// schemes. If no port is specified,
 * defaults to 80 for http and 443 for https.
 *
 * @return Tuple of (scheme_host_port, path_prefix)
 *   scheme_host_port: "https://host:port" or "http://host:port"
 *   path_prefix: any path after the host:port (e.g., "" or "/api")
 */
std::pair<std::string, std::string> parse_url(const std::string& url) {
    // Find scheme
    auto scheme_end = url.find("://");
    if (scheme_end == std::string::npos) {
        throw std::runtime_error("Invalid Manager URL (missing scheme): " + url);
    }

    std::string scheme = url.substr(0, scheme_end);
    if (scheme != "http" && scheme != "https") {
        throw std::runtime_error("Invalid Manager URL scheme (must be http or https): " + url);
    }

    // Find host:port and path
    auto host_start = scheme_end + 3;
    auto path_start = url.find('/', host_start);

    std::string scheme_host_port;
    std::string path_prefix;

    if (path_start == std::string::npos) {
        scheme_host_port = url;
        path_prefix = "";
    } else {
        scheme_host_port = url.substr(0, path_start);
        path_prefix = url.substr(path_start);
        // Remove trailing slash from path prefix
        if (!path_prefix.empty() && path_prefix.back() == '/') {
            path_prefix.pop_back();
        }
    }

    return {scheme_host_port, path_prefix};
}

} // namespace

ManagerRestClient::ManagerRestClient(std::string url, std::optional<std::string> ca_cert_path,
                                     std::chrono::milliseconds connect_timeout,
                                     std::chrono::milliseconds read_timeout)
    : url_(std::move(url)), ca_cert_path_(std::move(ca_cert_path)),
      connect_timeout_(connect_timeout), read_timeout_(read_timeout) {}

namespace {

/**
 * @brief Create and configure an httplib::Client for the given URL.
 *
 * httplib::Client handles both HTTP and HTTPS when compiled with OpenSSL.
 */
httplib::Client create_http_client(const std::string& scheme_host_port,
                                   const std::optional<std::string>& ca_cert_path,
                                   std::chrono::milliseconds connect_timeout,
                                   std::chrono::milliseconds read_timeout) {
    httplib::Client client(scheme_host_port);
    client.set_connection_timeout(connect_timeout);
    client.set_read_timeout(read_timeout);

    if (scheme_host_port.starts_with("https://")) {
        if (ca_cert_path.has_value() && !ca_cert_path->empty()) {
            client.set_ca_cert_path(ca_cert_path->c_str());
        }
        client.enable_server_certificate_verification(true);
    }

    return client;
}

} // namespace

void ManagerRestClient::authenticate(const std::string& username, const std::string& password) {
    auto [scheme_host_port, path_prefix] = parse_url(url_);
    auto client =
        create_http_client(scheme_host_port, ca_cert_path_, connect_timeout_, read_timeout_);

    // POST /api/v1/auth with form data
    std::string auth_path = path_prefix + "/api/v1/auth";
    httplib::Params params{{"username", username}, {"password", password}};

    LOG_DEBUG("Authenticating with Manager API at {}{}", scheme_host_port, auth_path);

    auto result = client.Post(auth_path, params);

    if (!result) {
        throw std::runtime_error("Manager API connection failed: " +
                                 httplib::to_string(result.error()));
    }

    if (result->status != 200) {
        throw std::runtime_error("Manager API authentication failed (HTTP " +
                                 std::to_string(result->status) + "): " + result->body);
    }

    // Parse token from response JSON: {"token": "..."}
    rapidjson::Document doc;
    doc.Parse(result->body.c_str());

    if (doc.HasParseError() || !doc.IsObject()) {
        throw std::runtime_error("Manager API auth response is not valid JSON");
    }

    if (!doc.HasMember("token") || !doc["token"].IsString()) {
        throw std::runtime_error("Manager API auth response missing 'token' field");
    }

    token_ = doc["token"].GetString();
    LOG_INFO("Authenticated with Manager API successfully");
}

std::string ManagerRestClient::fetchScenes() {
    if (token_.empty()) {
        throw std::runtime_error("Manager API not authenticated — call authenticate() first");
    }

    auto [scheme_host_port, path_prefix] = parse_url(url_);
    auto client =
        create_http_client(scheme_host_port, ca_cert_path_, connect_timeout_, read_timeout_);

    // GET /api/v1/scenes with auth header
    std::string scenes_path = path_prefix + "/api/v1/scenes";
    httplib::Headers headers = {{"Authorization", "Token " + token_}};

    LOG_DEBUG("Fetching scenes from Manager API: {}{}", scheme_host_port, scenes_path);

    auto result = client.Get(scenes_path, headers);

    if (!result) {
        throw std::runtime_error("Manager API connection failed: " +
                                 httplib::to_string(result.error()));
    }

    if (result->status != 200) {
        throw std::runtime_error("Manager API scenes request failed (HTTP " +
                                 std::to_string(result->status) + "): " + result->body);
    }

    LOG_INFO("Fetched scenes from Manager API ({} bytes)", result->body.size());
    return result->body;
}

} // namespace tracker
