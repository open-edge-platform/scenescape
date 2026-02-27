// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "manager_rest_client.hpp"

#include <gmock/gmock.h>

namespace tracker::test {

/**
 * @brief Mock Manager REST client for unit testing.
 *
 * Provides gmock methods for IManagerRestClient operations, allowing tests
 * to verify Manager API interactions without requiring a real server.
 */
class MockManagerRestClient : public IManagerRestClient {
public:
    MOCK_METHOD(void, authenticate, (const std::string&, const std::string&), (override));
    MOCK_METHOD(std::string, fetchScenes, (), (override));
};

} // namespace tracker::test
