// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstdlib>
#include <optional>
#include <string>

namespace tracker::test {

/**
 * @brief RAII helper for setting/unsetting environment variables in tests.
 *
 * Saves the original value (if any) on construction, sets the new value,
 * and restores the original value on destruction. This ensures test isolation
 * by automatically cleaning up environment changes.
 *
 * Usage:
 *   ScopedEnv env("MY_VAR", "value");     // Set to "value"
 *   ScopedEnv env("MY_VAR", "");          // Set to empty string
 *   ScopedEnv env("MY_VAR", std::nullopt); // Unset the variable
 */
class ScopedEnv {
public:
    /**
     * @brief Set or unset an environment variable for the scope's lifetime.
     *
     * @param name The environment variable name.
     * @param value The value to set, or std::nullopt to unset the variable.
     */
    ScopedEnv(const char* name, std::optional<const char*> value) : name_(name) {
        if (const char* old = std::getenv(name)) {
            old_value_ = old;
        }
        if (value) {
            setenv(name, *value, 1);
        } else {
            unsetenv(name);
        }
    }

    ~ScopedEnv() {
        if (old_value_) {
            setenv(name_, old_value_->c_str(), 1);
        } else {
            unsetenv(name_);
        }
    }

    // Non-copyable, non-movable
    ScopedEnv(const ScopedEnv&) = delete;
    ScopedEnv& operator=(const ScopedEnv&) = delete;
    ScopedEnv(ScopedEnv&&) = delete;
    ScopedEnv& operator=(ScopedEnv&&) = delete;

private:
    const char* name_;
    std::optional<std::string> old_value_;
};

} // namespace tracker::test
