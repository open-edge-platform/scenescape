// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <atomic>
#include <thread>

// Forward declaration
namespace httplib {
class Server;
}

namespace tracker {

/**
 * @brief HTTP healthcheck server for Kubernetes liveness and readiness probes.
 *
 * Runs a lightweight HTTP server on configurable port responding to:
 * - /healthz - Liveness probe (is process alive?)
 * - /readyz  - Readiness probe (is service ready to handle traffic?)
 *
 * Responses:
 * - 200 OK with {"status":"healthy"} when respective flag is true
 * - 503 Service Unavailable with {"status":"unhealthy"} when false
 *
 * Thread-safe: Uses atomic flags for health state management.
 *
 * Usage:
 *   std::atomic<bool> liveness{false};
 *   std::atomic<bool> readiness{false};
 *   HealthcheckServer server(8080, liveness, readiness);
 *   server.start();
 *
 *   liveness = true;    // Mark process alive
 *   readiness = true;   // Mark service ready (e.g., after MQTT connection)
 *
 *   // ... service runs ...
 *
 *   readiness = false;  // Mark not ready before shutdown
 *   server.stop();
 */
class HealthcheckServer {
public:
    /**
     * @brief Construct healthcheck server.
     * @param port Port to listen on (typically 8080)
     * @param liveness Reference to atomic flag for liveness status
     * @param readiness Reference to atomic flag for readiness status
     */
    HealthcheckServer(int port, std::atomic<bool>& liveness, std::atomic<bool>& readiness);

    /**
     * @brief Start healthcheck server in background thread.
     */
    void start();

    /**
     * @brief Stop healthcheck server gracefully.
     */
    void stop();

    /**
     * @brief Destructor ensures server is stopped.
     */
    ~HealthcheckServer();

    /**
     * @brief Generate healthz endpoint response.
     * @param is_healthy Liveness status flag
     * @return pair of HTTP status code and JSON response body
     */
    static std::pair<int, std::string> handle_healthz(bool is_healthy);

    /**
     * @brief Generate readyz endpoint response.
     * @param is_ready Readiness status flag
     * @return pair of HTTP status code and JSON response body
     */
    static std::pair<int, std::string> handle_readyz(bool is_ready);

private:
    void server_thread();

    int port_;
    std::atomic<bool>& liveness_;
    std::atomic<bool>& readiness_;
    std::atomic<bool> shutdown_requested_{false};
    std::thread thread_;
    httplib::Server* server_{nullptr}; // For graceful shutdown
};

} // namespace tracker
