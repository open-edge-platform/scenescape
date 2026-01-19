// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck_server.hpp"

#include <chrono>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <httplib.h>
#include <rapidjson/document.h>
#include <thread>

namespace tracker {
namespace {

/**
 * @brief Parse JSON string and validate structure.
 */
rapidjson::Document parse_json(const std::string& json_str) {
    rapidjson::Document doc;
    doc.Parse(json_str.c_str());
    return doc;
}

/**
 * @brief Test handle_healthz returns correct status codes and JSON.
 */
TEST(HealthcheckServerTest, HandleHealthz) {
    // Healthy state
    {
        auto [status_code, json_response] = HealthcheckServer::handle_healthz(true);
        EXPECT_EQ(status_code, 200);

        auto doc = parse_json(json_response);
        ASSERT_TRUE(doc.IsObject());
        ASSERT_TRUE(doc.HasMember("status"));
        EXPECT_STREQ(doc["status"].GetString(), "healthy");
    }

    // Unhealthy state
    {
        auto [status_code, json_response] = HealthcheckServer::handle_healthz(false);
        EXPECT_EQ(status_code, 503);

        auto doc = parse_json(json_response);
        ASSERT_TRUE(doc.IsObject());
        ASSERT_TRUE(doc.HasMember("status"));
        EXPECT_STREQ(doc["status"].GetString(), "unhealthy");
    }
}

/**
 * @brief Test handle_readyz returns correct status codes and JSON.
 */
TEST(HealthcheckServerTest, HandleReadyz) {
    // Ready state
    {
        auto [status_code, json_response] = HealthcheckServer::handle_readyz(true);
        EXPECT_EQ(status_code, 200);

        auto doc = parse_json(json_response);
        ASSERT_TRUE(doc.IsObject());
        ASSERT_TRUE(doc.HasMember("status"));
        EXPECT_STREQ(doc["status"].GetString(), "ready");
    }

    // Not ready state
    {
        auto [status_code, json_response] = HealthcheckServer::handle_readyz(false);
        EXPECT_EQ(status_code, 503);

        auto doc = parse_json(json_response);
        ASSERT_TRUE(doc.IsObject());
        ASSERT_TRUE(doc.HasMember("status"));
        EXPECT_STREQ(doc["status"].GetString(), "notready");
    }
}

// =============================================================================
// HealthcheckServer Lifecycle Tests
// =============================================================================

/**
 * @brief Test HealthcheckServer start() and stop() lifecycle.
 */
TEST(HealthcheckServerLifecycleTest, StartAndStop) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    HealthcheckServer server(19080, liveness, readiness);

    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    server.stop();

    SUCCEED();
}

/**
 * @brief Test double start() call is handled gracefully.
 */
TEST(HealthcheckServerLifecycleTest, DoubleStartProtection) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    HealthcheckServer server(19081, liveness, readiness);

    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    server.start(); // Second start should be a no-op

    server.stop();
    SUCCEED();
}

/**
 * @brief Test stop() on non-running server is safe.
 */
TEST(HealthcheckServerLifecycleTest, StopWithoutStart) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    HealthcheckServer server(19082, liveness, readiness);
    server.stop();
    SUCCEED();
}

/**
 * @brief Test destructor stops server cleanly.
 */
TEST(HealthcheckServerLifecycleTest, DestructorStopsServer) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    {
        HealthcheckServer server(19083, liveness, readiness);
        server.start();
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    SUCCEED();
}

/**
 * @brief Test actual HTTP requests to running HealthcheckServer.
 */
TEST(HealthcheckServerLifecycleTest, ActualHttpRequests) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{true};

    HealthcheckServer server(19084, liveness, readiness);
    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    httplib::Client client("localhost", 19084);
    client.set_connection_timeout(1, 0);

    // Test /healthz endpoint
    auto healthz_res = client.Get("/healthz");
    ASSERT_TRUE(healthz_res);
    EXPECT_EQ(healthz_res->status, 200);

    auto healthz_doc = parse_json(healthz_res->body);
    EXPECT_STREQ(healthz_doc["status"].GetString(), "healthy");

    // Test /readyz endpoint
    auto readyz_res = client.Get("/readyz");
    ASSERT_TRUE(readyz_res);
    EXPECT_EQ(readyz_res->status, 200);

    auto readyz_doc = parse_json(readyz_res->body);
    EXPECT_STREQ(readyz_doc["status"].GetString(), "ready");

    server.stop();
}

/**
 * @brief Test HTTP responses when server reports unhealthy/not ready.
 */
TEST(HealthcheckServerLifecycleTest, UnhealthyHttpResponses) {
    std::atomic<bool> liveness{false};
    std::atomic<bool> readiness{false};

    HealthcheckServer server(19085, liveness, readiness);
    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    httplib::Client client("localhost", 19085);
    client.set_connection_timeout(1, 0);

    auto healthz_res = client.Get("/healthz");
    ASSERT_TRUE(healthz_res);
    EXPECT_EQ(healthz_res->status, 503);

    auto healthz_doc = parse_json(healthz_res->body);
    EXPECT_STREQ(healthz_doc["status"].GetString(), "unhealthy");

    auto readyz_res = client.Get("/readyz");
    ASSERT_TRUE(readyz_res);
    EXPECT_EQ(readyz_res->status, 503);

    auto readyz_doc = parse_json(readyz_res->body);
    EXPECT_STREQ(readyz_doc["status"].GetString(), "notready");

    server.stop();
}

/**
 * @brief Test atomic flag changes are reflected in responses.
 */
TEST(HealthcheckServerLifecycleTest, DynamicStateChanges) {
    std::atomic<bool> liveness{true};
    std::atomic<bool> readiness{false};

    HealthcheckServer server(19086, liveness, readiness);
    server.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    httplib::Client client("localhost", 19086);
    client.set_connection_timeout(1, 0);

    // Initially: healthy but not ready
    auto res1 = client.Get("/healthz");
    ASSERT_TRUE(res1);
    EXPECT_EQ(res1->status, 200);

    auto res2 = client.Get("/readyz");
    ASSERT_TRUE(res2);
    EXPECT_EQ(res2->status, 503);

    // Change readiness to true
    readiness = true;
    auto res3 = client.Get("/readyz");
    ASSERT_TRUE(res3);
    EXPECT_EQ(res3->status, 200);

    // Change liveness to false
    liveness = false;
    auto res4 = client.Get("/healthz");
    ASSERT_TRUE(res4);
    EXPECT_EQ(res4->status, 503);

    server.stop();
}

} // namespace
} // namespace tracker
