// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck.hpp"
#include "healthcheck_command.hpp"

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
 * @brief Test endpoint normalization adds leading slash.
 */
TEST(HealthcheckCommandTest, EndpointNormalizationAddsSlash) {
    std::string received_endpoint;

    auto mock_http_get = [&received_endpoint](const std::string& endpoint, int port) {
        received_endpoint = endpoint;
        return create_mock_response(200);
    };

    run_healthcheck_command("healthz", 8080, mock_http_get);
    EXPECT_EQ(received_endpoint, "/healthz");
}

/**
 * @brief Test endpoint normalization preserves existing leading slash.
 */
TEST(HealthcheckCommandTest, EndpointNormalizationPreservesSlash) {
    std::string received_endpoint;

    auto mock_http_get = [&received_endpoint](const std::string& endpoint, int port) {
        received_endpoint = endpoint;
        return create_mock_response(200);
    };

    run_healthcheck_command("/readyz", 8080, mock_http_get);
    EXPECT_EQ(received_endpoint, "/readyz");
}

/**
 * @brief Test endpoint normalization with empty string.
 */
TEST(HealthcheckCommandTest, EndpointNormalizationEmptyString) {
    std::string received_endpoint;

    auto mock_http_get = [&received_endpoint](const std::string& endpoint, int port) {
        received_endpoint = endpoint;
        return create_mock_response(200);
    };

    run_healthcheck_command("", 8080, mock_http_get);
    EXPECT_EQ(received_endpoint, "");
}

/**
 * @brief Test various HTTP error status codes return 1.
 */
TEST(HealthcheckCommandTest, Various4xxErrors) {
    std::vector<int> error_codes = {400, 404, 500, 502, 503, 504};

    for (int code : error_codes) {
        auto mock_http_get = [code](const std::string& endpoint, int port) {
            return create_mock_response(code);
        };

        int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
        EXPECT_EQ(result, 1) << "Failed for status code: " << code;
    }
}

/**
 * @brief Test timeout error returns 1.
 */
TEST(HealthcheckCommandTest, TimeoutError) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_failed_response(httplib::Error::Read);
    };

    int result = run_healthcheck_command("/readyz", 8080, mock_http_get);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test different endpoint paths.
 */
TEST(HealthcheckCommandTest, DifferentEndpoints) {
    std::vector<std::string> endpoints = {"/healthz", "/readyz", "/status", "/health"};

    for (const auto& endpoint : endpoints) {
        std::string received_endpoint;

        auto mock_http_get = [&received_endpoint](const std::string& ep, int port) {
            received_endpoint = ep;
            return create_mock_response(200);
        };

        run_healthcheck_command(endpoint, 8080, mock_http_get);
        EXPECT_EQ(received_endpoint, endpoint);
    }
}

/**
 * @brief Test 201 Created status is not considered success (only 200).
 */
TEST(HealthcheckCommandTest, Status201NotSuccess) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(201);
    };

    int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test 204 No Content is not considered success (only 200).
 */
TEST(HealthcheckCommandTest, Status204NotSuccess) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(204);
    };

    int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test null response returns 1.
 */
TEST(HealthcheckCommandTest, NullResponse) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_failed_response(httplib::Error::Unknown);
    };

    int result = run_healthcheck_command("/healthz", 8080, mock_http_get);
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
 * @brief Test multiple sequential calls work correctly.
 */
TEST(HealthcheckCommandTest, SequentialCalls) {
    auto mock_http_get = [](const std::string& endpoint, int port) {
        return create_mock_response(200);
    };

    int result1 = run_healthcheck_command("/healthz", 8080, mock_http_get);
    int result2 = run_healthcheck_command("/readyz", 8080, mock_http_get);
    int result3 = run_healthcheck_command("/healthz", 9090, mock_http_get);

    EXPECT_EQ(result1, 0);
    EXPECT_EQ(result2, 0);
    EXPECT_EQ(result3, 0);
}

/**
 * @brief Test alternating success/failure calls.
 */
TEST(HealthcheckCommandTest, AlternatingSuccessFailure) {
    int call_count = 0;

    auto mock_http_get = [&call_count](const std::string& endpoint, int port) {
        call_count++;
        if (call_count % 2 == 0) {
            return create_mock_response(200);
        } else {
            return create_mock_response(503);
        }
    };

    int result1 = run_healthcheck_command("/healthz", 8080, mock_http_get);
    int result2 = run_healthcheck_command("/healthz", 8080, mock_http_get);
    int result3 = run_healthcheck_command("/healthz", 8080, mock_http_get);
    int result4 = run_healthcheck_command("/healthz", 8080, mock_http_get);

    EXPECT_EQ(result1, 1); // First call (503)
    EXPECT_EQ(result2, 0); // Second call (200)
    EXPECT_EQ(result3, 1); // Third call (503)
    EXPECT_EQ(result4, 0); // Fourth call (200)
}

/**
 * @brief Test default HTTP GET function is not called when mock provided.
 */
TEST(HealthcheckCommandTest, MockOverridesDefault) {
    bool mock_called = false;

    auto mock_http_get = [&mock_called](const std::string& endpoint, int port) {
        mock_called = true;
        return create_mock_response(200);
    };

    run_healthcheck_command("/healthz", 8080, mock_http_get);
    EXPECT_TRUE(mock_called);
}

/**
 * @brief Test endpoint normalization with various slash combinations.
 */
TEST(HealthcheckCommandTest, EndpointSlashVariations) {
    std::vector<std::pair<std::string, std::string>> test_cases = {
        {"healthz", "/healthz"},
        {"/healthz", "/healthz"},
        {"//healthz", "//healthz"}, // Already has slash, not modified
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
// Integration tests with real HealthServer (covers make_http_request)
// =============================================================================

/**
 * @brief Test run_healthcheck_command with real HTTP request (no mock).
 * This exercises make_http_request() and the default http_get=nullptr branch.
 */
TEST(HealthcheckCommandIntegrationTest, RealHttpRequest) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    // Start a real HealthServer
    tracker::HealthServer server(19090, liveness, readiness);
    server.start();

    // Give server time to start
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Call run_healthcheck_command with nullptr (uses default make_http_request)
    int result = run_healthcheck_command("/healthz", 19090, nullptr);
    EXPECT_EQ(result, 0);

    // Test readyz endpoint
    int result2 = run_healthcheck_command("/readyz", 19090, nullptr);
    EXPECT_EQ(result2, 0);

    server.stop();
}

/**
 * @brief Test run_healthcheck_command returns failure when service unhealthy.
 */
TEST(HealthcheckCommandIntegrationTest, RealHttpRequestUnhealthy) {
    std::atomic<bool> liveness{false};
    std::atomic<bool> readiness{false};

    tracker::HealthServer server(19091, liveness, readiness);
    server.start();

    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Should return 1 because server reports unhealthy (503)
    int result = run_healthcheck_command("/healthz", 19091, nullptr);
    EXPECT_EQ(result, 1);

    server.stop();
}

/**
 * @brief Test run_healthcheck_command returns failure when connection refused.
 */
TEST(HealthcheckCommandIntegrationTest, ConnectionRefused) {
    // No server running on this port
    int result = run_healthcheck_command("/healthz", 19099, nullptr);
    EXPECT_EQ(result, 1);
}

/**
 * @brief Test make_http_request function directly.
 */
TEST(HealthcheckCommandIntegrationTest, MakeHttpRequestDirect) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    tracker::HealthServer server(19092, liveness, readiness);
    server.start();

    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Call make_http_request directly
    auto result = make_http_request("/healthz", 19092);
    ASSERT_TRUE(result);
    EXPECT_EQ(result->status, 200);

    server.stop();
}

} // namespace
} // namespace tracker
