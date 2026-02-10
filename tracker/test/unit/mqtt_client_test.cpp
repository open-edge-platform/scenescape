// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @file mqtt_client_test.cpp
 * @brief Unit tests for MqttClient pure/static functions.
 *        CallbackGuard thread-safety is tested in callback_guard_test.cpp.
 *
 * Coverage Strategy:
 * ------------------
 * The MqttClient class cannot be instantiated in unit tests because the Paho MQTT
 * library requires a valid broker endpoint and causes segfaults in isolated test
 * environments. Only pure/static functions are tested here:
 *   - generateClientId(): Client ID format validation
 *   - MQTT_QOS constant: At-least-once delivery semantics
 *
 * Reconnection after initial connect uses a simple fixed-delay retry thread.
 * Post-connection loss reconnection is handled by Paho's built-in auto-reconnect.
 * Thread-safety mechanisms (CallbackGuard) are tested in callback_guard_test.cpp.
 *
 * Full integration testing of MqttClient (connection, pub/sub, reconnection, TLS)
 * is performed in test/service/test_mqtt_client_service.cpp which uses a real
 * Docker-based MQTT broker.
 *
 * The mqtt_client.cpp implementation is excluded from unit test coverage metrics
 * in the Makefile. This is intentional - the extracted pure logic is tested here,
 * and the network-dependent code is covered by service tests.
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "mqtt_client.hpp"

#include <regex>

namespace tracker {
namespace {

class MqttClientTest : public ::testing::Test {
protected:
    MqttConfig createInsecureConfig() {
        MqttConfig config;
        config.host = "localhost";
        config.port = 1883;
        config.insecure = true;
        return config;
    }

    MqttConfig createSecureConfig() {
        MqttConfig config;
        config.host = "broker.example.com";
        config.port = 8883;
        config.insecure = false;
        config.tls = TlsConfig{.ca_cert_path = "/path/to/ca.crt",
                               .client_cert_path = "/path/to/client.crt",
                               .client_key_path = "/path/to/client.key",
                               .verify_server = true};
        return config;
    }
};

// Test client ID generation format: tracker-{hostname}-{pid}
TEST_F(MqttClientTest, GenerateClientId_HasCorrectFormat) {
    std::string client_id = MqttClient::generateClientId();

    // Should start with "tracker-"
    EXPECT_THAT(client_id, ::testing::StartsWith("tracker-"));

    // Should match pattern: tracker-{hostname}-{pid}
    // hostname can contain alphanumeric and hyphens, pid is numeric
    std::regex pattern(R"(tracker-[a-zA-Z0-9._-]+-\d+)");
    EXPECT_TRUE(std::regex_match(client_id, pattern))
        << "Client ID '" << client_id << "' doesn't match expected pattern";
}

TEST_F(MqttClientTest, GenerateClientId_IsConsistent) {
    std::string id1 = MqttClient::generateClientId();
    std::string id2 = MqttClient::generateClientId();

    // Same process should generate same ID
    EXPECT_EQ(id1, id2);
}

// =============================================================================
// MQTT_QOS constant test
// =============================================================================

TEST_F(MqttClientTest, MqttQos_IsAtLeastOnce) {
    // QoS 1 = at-least-once delivery (messages may be duplicated but not lost)
    // This is the correct choice for tracker telemetry
    EXPECT_EQ(MqttClient::MQTT_QOS, 1);
}

} // namespace
} // namespace tracker
