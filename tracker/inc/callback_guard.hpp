// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <atomic>

namespace tracker {

/**
 * @brief RAII guard for tracking in-flight async callbacks during shutdown.
 *
 * Increments a counter on construction, decrements on destruction.
 * Captures the stop flag at construction time so shouldSkip() is
 * consistent for the lifetime of the guard.
 *
 * Usage:
 *   CallbackGuard guard(in_flight_counter, stop_flag);
 *   if (guard.shouldSkip()) return;
 *   // ... callback body ...
 */
class CallbackGuard {
public:
    /**
     * @brief Construct guard, atomically incrementing in-flight counter.
     *
     * @param counter Atomic counter tracking active callbacks
     * @param stop_flag Atomic flag indicating shutdown in progress
     */
    explicit CallbackGuard(std::atomic<int>& counter, const std::atomic<bool>& stop_flag)
        : counter_(counter), should_skip_(stop_flag.load()) {
        ++counter_;
    }

    ~CallbackGuard() { --counter_; }

    /**
     * @brief Check if the callback should early-return due to shutdown.
     *
     * Value is captured at construction time and does not change.
     */
    [[nodiscard]] bool shouldSkip() const { return should_skip_; }

    CallbackGuard(const CallbackGuard&) = delete;
    CallbackGuard& operator=(const CallbackGuard&) = delete;
    CallbackGuard(CallbackGuard&&) = delete;
    CallbackGuard& operator=(CallbackGuard&&) = delete;

private:
    std::atomic<int>& counter_;
    bool should_skip_;
};

} // namespace tracker
