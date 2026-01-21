// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck_command.hpp"
#include "healthcheck_server.hpp"

#include <atomic>
#include <chrono>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <httplib.h>
#include <memory>
#include <thread>

namespace tracker {
namespace {

/**
 * @brief Create a mock HTTP response with given status code.
 */
httplib::Result create_mock_response(int status_code, const std::string& body = "") {
    auto res = std::make_unique<httplib::Response>();
    res->status = status_code;
    res->body = body;
    return httplib::Result(std::move(res), httplib::Error::Success, httplib::Headers());
}

/**
 * @brief Create a failed HTTP response (connection error).
 */
httplib::Result create_failed_response(httplib::Error error = httplib::Error::Connection) {
    return httplib::Result(nullptr, error, httplib::Headers());
}

/**
 * @brief Test successful health check returns 0.
 */
TEST(HealthcheckCommandTest, SuccessfulRequest) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(200, R"({"status":"healthy"})");
    };

    int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
    EXPECT_EQ(result, 0);
}

/**
 * @brief Test unhealthy response returns 1.
 */
TEST(HealthcheckCommandTest, UnhealthyResponse) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(503, R"({"status":"unhealthy"})");
    };

    int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test connection failure returns 1.
 */
TEST(HealthcheckCommandTest, ConnectionFailure) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_failed_response(httplib::Error::Connection);
    };

    int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test empty endpoint returns failure.
 */
TEST(HealthcheckCommandTest, EmptyEndpointFails) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(200);
    };

    int result = run_healthcheck_command("", 8080, mock_http_get);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test invalid port values return failure.
 */
TEST(HealthcheckCommandTest, InvalidPortValues) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(200);
    };

    // Port zero
    EXPECT_EQ(run_healthcheck_command("/healthz", 0, mock_http_get), 1);

    // Negative port
    EXPECT_EQ(run_healthcheck_command("/healthz", -1, mock_http_get), 1);

    // Above max port
    EXPECT_EQ(run_healthcheck_command("/healthz", 65536, mock_http_get), 1);
}

/**
 * @brief Test valid port boundaries (1 and 65535) succeed.
 */
TEST(HealthcheckCommandTest, ValidPortBoundaries) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(200);
    };

    EXPECT_EQ(run_healthcheck_command("/healthz", 1, mock_http_get), 0);
    EXPECT_EQ(run_healthcheck_command("/healthz", 65535, mock_http_get), 0);
}

/**
 * @brief Test nullptr http_get function returns failure.
 */
TEST(HealthcheckCommandTest, NullHttpGetFails) {
    int result = run_healthcheck_command("/healthz", 8080, nullptr);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test various non-200 HTTP status codes return 1.
 */
TEST(HealthcheckCommandTest, NonSuccessStatusCodes) {
    std::vector<int> error_codes = {201, 204, 400, 404, 500, 502, 503, 504};

    for (int code : error_codes) {
        auto mock_http_get = [code](const std::string& endpoint, int port) {
            return create_mock_response(code);
        };

        int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
        EXPECT_EQ(result, 1) << "Failed for status code: " << code;
    }
}

/**
 * @brief Test timeout/read error returns 1.
 */
TEST(HealthcheckCommandTest, TimeoutError) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_failed_response(httplib::Error::Read);
    };

    int result = run_healthcheck_command("/readyz", 8080, mock_http_get);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test response body content is ignored (only status code matters).
 */
TEST(HealthcheckCommandTest, ResponseBodyIgnored) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(200, "invalid json {{{");
    };

    int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
    EXPECT_EQ(result, 0); // Should succeed despite invalid body
}

/**
 * @brief Test endpoint normalization with various slash combinations.
 */
TEST(HealthcheckCommandTest, EndpointSlashVariations) {
    std::vector<std::pair<std::string, std::string>> test_cases = {{"healthz", "/healthz"},
                                                                   {"/healthz", "/healthz"},
                                                                   {"//healthz", "//healthz"},
                                                                   {"/health/sub", "/health/sub"},
                                                                   {"health/sub", "/health/sub"}};

    for (const auto& [input, expected] : test_cases) {
        std::string received_endpoint;

        auto mock_http_get = [&received_endpoint](const std::string& endpoint, int port) {
            received_endpoint = endpoint;
            return create_mock_response(200);
        };

        run_healthcheck_command(input, 8080, mock_http_get);
        EXPECT_EQ(received_endpoint, expected) << "Failed for input: " << input;
    }
}

// =============================================================================
// Integration tests with real HealthcheckServer (covers make_http_request)
// =============================================================================

/**
 * @brief Test run_healthcheck_command with real HTTP request (no mock).
 */
TEST(HealthcheckCommandIntegrationTest, RealHttpRequest) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    tracker::HealthcheckServer server(19090, liveness, readiness);
    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    int result = run_healthcheck_command("/healthz", 19090);
    EXPECT_EQ(result, 0);

    int result2 = run_healthcheck_command("/readyz", 19090);
    EXPECT_EQ(result2, 0);

    server.stop();
}

/**
 * @brief Test run_healthcheck_command returns failure when service unhealthy.
 */
TEST(HealthcheckCommandIntegrationTest, RealHttpRequestUnhealthy) {
    std::atomic<bool> liveness{false};
    std::atomic<bool> readiness{false};

    tracker::HealthcheckServer server(19091, liveness, readiness);
    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    int result = run_healthcheck_command("/healthz", 19091);
    EXPECT_EQ(result, 1);

    server.stop();
}

/**
 * @brief Test run_healthcheck_command returns failure when connection refused.
 */
TEST(HealthcheckCommandIntegrationTest, ConnectionRefused) {
    int result = run_healthcheck_command("/healthz", 19099);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test make_http_request function directly.
 */
TEST(HealthcheckCommandIntegrationTest, MakeHttpRequestDirect) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    tracker::HealthcheckServer server(19092, liveness, readiness);
    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    auto result = make_http_request("/healthz", 19092);
    ASSERT_TRUE(result);
    EXPECT_EQ(result->status, 200);

    server.stop();
}

} // namespace
} // namespace tracker
