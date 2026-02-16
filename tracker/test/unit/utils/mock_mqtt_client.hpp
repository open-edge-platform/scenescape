// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "mqtt_client.hpp"

#include <gmock/gmock.h>

namespace tracker::test {

/**
 * @brief Mock MQTT client for unit testing.
 *
 * Provides gmock methods for all IMqttClient operations, allowing tests
 * to verify MQTT interactions without requiring a real broker.
 */
class MockMqttClient : public IMqttClient {
public:
  MOCK_METHOD(void, connect, (), (override));
  MOCK_METHOD(void, disconnect, (std::chrono::milliseconds), (override));
  MOCK_METHOD(void, subscribe, (const std::string&), (override));
  MOCK_METHOD(void, unsubscribe, (const std::string&), (override));
  MOCK_METHOD(void, publish, (const std::string&, const std::string&), (override));
  MOCK_METHOD(void, setMessageCallback, (MessageCallback), (override));
  MOCK_METHOD(bool, isConnected, (), (const, override));
  MOCK_METHOD(bool, isSubscribed, (), (const, override));
};

} // namespace tracker::test
