// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

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

// Note: Tests that construct MqttClient objects are deferred to service tests
// because the Paho MQTT library requires a valid broker endpoint and causes
// segfaults in isolated unit test environments. See test/service/test_tracker_mqtt.py

} // namespace
} // namespace tracker
