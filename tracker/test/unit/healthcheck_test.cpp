// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck.hpp"

#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <rapidjson/document.h>

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
 * @brief Test handle_healthz returns 200 when healthy.
 */
TEST(HealthServerTest, HandleHealthzHealthy) {
    auto [status_code, json_response] = HealthServer::handle_healthz(true);

    EXPECT_EQ(status_code, 200);

    auto doc = parse_json(json_response);
    ASSERT_TRUE(doc.IsObject());
    ASSERT_TRUE(doc.HasMember("status"));
    EXPECT_STREQ(doc["status"].GetString(), "healthy");
}

/**
 * @brief Test handle_healthz returns 503 when unhealthy.
 */
TEST(HealthServerTest, HandleHealthzUnhealthy) {
    auto [status_code, json_response] = HealthServer::handle_healthz(false);

    EXPECT_EQ(status_code, 503);

    auto doc = parse_json(json_response);
    ASSERT_TRUE(doc.IsObject());
    ASSERT_TRUE(doc.HasMember("status"));
    EXPECT_STREQ(doc["status"].GetString(), "unhealthy");
}

/**
 * @brief Test handle_readyz returns 200 when ready.
 */
TEST(HealthServerTest, HandleReadyzReady) {
    auto [status_code, json_response] = HealthServer::handle_readyz(true);

    EXPECT_EQ(status_code, 200);

    auto doc = parse_json(json_response);
    ASSERT_TRUE(doc.IsObject());
    ASSERT_TRUE(doc.HasMember("status"));
    EXPECT_STREQ(doc["status"].GetString(), "ready");
}

/**
 * @brief Test handle_readyz returns 503 when not ready.
 */
TEST(HealthServerTest, HandleReadyzNotReady) {
    auto [status_code, json_response] = HealthServer::handle_readyz(false);

    EXPECT_EQ(status_code, 503);

    auto doc = parse_json(json_response);
    ASSERT_TRUE(doc.IsObject());
    ASSERT_TRUE(doc.HasMember("status"));
    EXPECT_STREQ(doc["status"].GetString(), "notready");
}

/**
 * @brief Test handle_healthz JSON format is valid.
 */
TEST(HealthServerTest, HandleHealthzJsonFormat) {
    auto [status_code, json_response] = HealthServer::handle_healthz(true);

    // Verify JSON is well-formed
    auto doc = parse_json(json_response);
    EXPECT_FALSE(doc.HasParseError());
    EXPECT_TRUE(doc.IsObject());
    EXPECT_EQ(doc.MemberCount(), 1); // Only "status" field
}

/**
 * @brief Test handle_readyz JSON format is valid.
 */
TEST(HealthServerTest, HandleReadyzJsonFormat) {
    auto [status_code, json_response] = HealthServer::handle_readyz(false);

    // Verify JSON is well-formed
    auto doc = parse_json(json_response);
    EXPECT_FALSE(doc.HasParseError());
    EXPECT_TRUE(doc.IsObject());
    EXPECT_EQ(doc.MemberCount(), 1); // Only "status" field
}

/**
 * @brief Test handle_healthz with different boolean states.
 */
TEST(HealthServerTest, HandleHealthzBooleanTransitions) {
    // Test true -> false transition
    auto [status1, json1] = HealthServer::handle_healthz(true);
    EXPECT_EQ(status1, 200);

    auto [status2, json2] = HealthServer::handle_healthz(false);
    EXPECT_EQ(status2, 503);

    // Test false -> true transition
    auto [status3, json3] = HealthServer::handle_healthz(false);
    EXPECT_EQ(status3, 503);

    auto [status4, json4] = HealthServer::handle_healthz(true);
    EXPECT_EQ(status4, 200);
}

/**
 * @brief Test handle_readyz with different boolean states.
 */
TEST(HealthServerTest, HandleReadyzBooleanTransitions) {
    // Test true -> false transition
    auto [status1, json1] = HealthServer::handle_readyz(true);
    EXPECT_EQ(status1, 200);

    auto [status2, json2] = HealthServer::handle_readyz(false);
    EXPECT_EQ(status2, 503);

    // Test false -> true transition
    auto [status3, json3] = HealthServer::handle_readyz(false);
    EXPECT_EQ(status3, 503);

    auto [status4, json4] = HealthServer::handle_readyz(true);
    EXPECT_EQ(status4, 200);
}

/**
 * @brief Test HealthServer construction with atomic flags.
 */
TEST(HealthServerTest, ConstructorWithAtomicFlags) {
    std::atomic<bool> liveness{false};
    std::atomic<bool> readiness{false};

    // Constructor should not throw
    EXPECT_NO_THROW({ HealthServer server(8080, liveness, readiness); });
}

/**
 * @brief Test HealthServer construction with different port values.
 */
TEST(HealthServerTest, ConstructorWithDifferentPorts) {
    std::atomic<bool> liveness{false};
    std::atomic<bool> readiness{false};

    EXPECT_NO_THROW({
        HealthServer server1(8080, liveness, readiness);
        HealthServer server2(9090, liveness, readiness);
        HealthServer server3(1024, liveness, readiness);
        HealthServer server4(65535, liveness, readiness);
    });
}

/**
 * @brief Test JSON response content type compatibility.
 */
TEST(HealthServerTest, JsonResponseContentType) {
    auto [status, json] = HealthServer::handle_healthz(true);

    // Verify JSON can be parsed by standard parser
    auto doc = parse_json(json);
    EXPECT_FALSE(doc.HasParseError());
}

/**
 * @brief Test consistent response format between handlers.
 */
TEST(HealthServerTest, ConsistentResponseFormat) {
    auto [healthz_status, healthz_json] = HealthServer::handle_healthz(true);
    auto [readyz_status, readyz_json] = HealthServer::handle_readyz(true);

    // Both should have same status code when true
    EXPECT_EQ(healthz_status, readyz_status);

    // Both should have valid JSON with "status" field
    auto healthz_doc = parse_json(healthz_json);
    auto readyz_doc = parse_json(readyz_json);

    EXPECT_TRUE(healthz_doc.HasMember("status"));
    EXPECT_TRUE(readyz_doc.HasMember("status"));
}

/**
 * @brief Test all status code paths are correct (branch coverage).
 */
TEST(HealthServerTest, AllStatusCodeBranches) {
    // Test all four combinations of status codes
    auto [h_ok, _1] = HealthServer::handle_healthz(true);
    auto [h_err, _2] = HealthServer::handle_healthz(false);
    auto [r_ok, _3] = HealthServer::handle_readyz(true);
    auto [r_err, _4] = HealthServer::handle_readyz(false);

    EXPECT_EQ(h_ok, 200);
    EXPECT_EQ(h_err, 503);
    EXPECT_EQ(r_ok, 200);
    EXPECT_EQ(r_err, 503);
}

/**
 * @brief Test all status string paths are correct (branch coverage).
 */
TEST(HealthServerTest, AllStatusStringBranches) {
    auto [_1, h_true] = HealthServer::handle_healthz(true);
    auto [_2, h_false] = HealthServer::handle_healthz(false);
    auto [_3, r_true] = HealthServer::handle_readyz(true);
    auto [_4, r_false] = HealthServer::handle_readyz(false);

    auto doc1 = parse_json(h_true);
    auto doc2 = parse_json(h_false);
    auto doc3 = parse_json(r_true);
    auto doc4 = parse_json(r_false);

    EXPECT_STREQ(doc1["status"].GetString(), "healthy");
    EXPECT_STREQ(doc2["status"].GetString(), "unhealthy");
    EXPECT_STREQ(doc3["status"].GetString(), "ready");
    EXPECT_STREQ(doc4["status"].GetString(), "notready");
}

} // namespace
} // namespace tracker
