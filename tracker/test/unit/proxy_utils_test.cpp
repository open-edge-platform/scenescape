// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "proxy_utils.hpp"

#include "utils/scoped_env.hpp"

#include <gtest/gtest.h>

#include <cstdlib>

namespace tracker {
namespace {

using test::ScopedEnv;

// =============================================================================
// clearEmptyProxyEnvVars() tests
// =============================================================================

TEST(ProxyUtilsTest, ClearEmptyProxyEnvVars_UnsetsEmptyVars) {
    // Set proxy variables to empty strings
    ScopedEnv http_lower("http_proxy", "");
    ScopedEnv http_upper("HTTP_PROXY", "");
    ScopedEnv https_lower("https_proxy", "");
    ScopedEnv https_upper("HTTPS_PROXY", "");
    ScopedEnv no_lower("no_proxy", "");
    ScopedEnv no_upper("NO_PROXY", "");

    // Verify they are set (to empty strings)
    EXPECT_NE(std::getenv("http_proxy"), nullptr);
    EXPECT_STREQ(std::getenv("http_proxy"), "");

    clearEmptyProxyEnvVars();

    // Verify all empty vars are now unset
    EXPECT_EQ(std::getenv("http_proxy"), nullptr);
    EXPECT_EQ(std::getenv("HTTP_PROXY"), nullptr);
    EXPECT_EQ(std::getenv("https_proxy"), nullptr);
    EXPECT_EQ(std::getenv("HTTPS_PROXY"), nullptr);
    EXPECT_EQ(std::getenv("no_proxy"), nullptr);
    EXPECT_EQ(std::getenv("NO_PROXY"), nullptr);
}

TEST(ProxyUtilsTest, ClearEmptyProxyEnvVars_PreservesNonEmptyVars) {
    // Set proxy variables to actual values
    ScopedEnv http_lower("http_proxy", "http://proxy:8080");
    ScopedEnv https_lower("https_proxy", "https://proxy:8443");

    clearEmptyProxyEnvVars();

    // Verify non-empty vars are preserved
    EXPECT_STREQ(std::getenv("http_proxy"), "http://proxy:8080");
    EXPECT_STREQ(std::getenv("https_proxy"), "https://proxy:8443");
}

TEST(ProxyUtilsTest, ClearEmptyProxyEnvVars_MixedEmptyAndNonEmpty) {
    // Mix of empty and non-empty
    ScopedEnv http_lower("http_proxy", "");                     // empty - should be cleared
    ScopedEnv https_lower("https_proxy", "https://proxy:8443"); // non-empty - should be preserved

    clearEmptyProxyEnvVars();

    // Empty var unset, non-empty preserved
    EXPECT_EQ(std::getenv("http_proxy"), nullptr);
    EXPECT_STREQ(std::getenv("https_proxy"), "https://proxy:8443");
}

TEST(ProxyUtilsTest, ClearEmptyProxyEnvVars_NoOpWhenNotSet) {
    // Ensure vars are not set
    ScopedEnv http_lower("http_proxy", std::nullopt);
    ScopedEnv https_lower("https_proxy", std::nullopt);

    // Should not crash when vars don't exist
    clearEmptyProxyEnvVars();

    // Still not set
    EXPECT_EQ(std::getenv("http_proxy"), nullptr);
    EXPECT_EQ(std::getenv("https_proxy"), nullptr);
}

} // namespace
} // namespace tracker
