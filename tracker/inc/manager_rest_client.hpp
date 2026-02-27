// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <optional>
#include <string>

namespace tracker {

/**
 * @brief Abstract interface for Manager REST API operations.
 *
 * Enables dependency injection and mock-based testing of components
 * that depend on the Manager API (e.g., ApiSceneLoader).
 */
class IManagerRestClient {
public:
    virtual ~IManagerRestClient() = default;

    /**
     * @brief Authenticate with the Manager API.
     *
     * @param username API username
     * @param password API password
     * @throws std::runtime_error on connection failure, HTTP error, or auth rejection
     */
    virtual void authenticate(const std::string& username, const std::string& password) = 0;

    /**
     * @brief Fetch all scenes from the Manager API.
     *
     * @return Raw JSON response body string
     * @throws std::runtime_error if not authenticated, connection fails, or HTTP error
     */
    virtual std::string fetchScenes() = 0;
};

/**
 * @brief HTTP client for Manager REST API.
 *
 * Handles authentication and scene fetching from the SceneScape Manager.
 * Supports HTTPS with CA certificate verification.
 */
class ManagerRestClient : public IManagerRestClient {
public:
    /**
     * @brief Construct a Manager REST API client.
     *
     * @param url Manager API base URL (e.g., "https://web.scenescape.intel.com")
     * @param ca_cert_path Optional CA certificate path for HTTPS verification
     * @param connect_timeout TCP connect timeout (default: 10s)
     * @param read_timeout HTTP read timeout (default: 30s)
     */
    ManagerRestClient(std::string url, std::optional<std::string> ca_cert_path = std::nullopt,
                      std::chrono::milliseconds connect_timeout = std::chrono::seconds(10),
                      std::chrono::milliseconds read_timeout = std::chrono::seconds(30));

    void authenticate(const std::string& username, const std::string& password) override;
    std::string fetchScenes() override;

private:
    std::string url_;
    std::optional<std::string> ca_cert_path_;
    std::string token_;
    std::chrono::milliseconds connect_timeout_;
    std::chrono::milliseconds read_timeout_;
};

} // namespace tracker
