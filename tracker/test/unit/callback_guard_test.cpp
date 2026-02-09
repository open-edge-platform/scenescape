// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "callback_guard.hpp"

#include <gtest/gtest.h>

#include <atomic>
#include <thread>
#include <vector>

namespace tracker {
namespace {

// =============================================================================
// RAII counter behavior
// =============================================================================

TEST(CallbackGuardTest, Constructor_IncrementsCounter) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{false};

    {
        CallbackGuard guard(counter, stop);
        EXPECT_EQ(counter.load(), 1);
    }
}

TEST(CallbackGuardTest, Destructor_DecrementsCounter) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{false};

    {
        CallbackGuard guard(counter, stop);
        EXPECT_EQ(counter.load(), 1);
    }
    EXPECT_EQ(counter.load(), 0);
}

TEST(CallbackGuardTest, MultipleGuards_IncrementCounterCorrectly) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{false};

    {
        CallbackGuard guard1(counter, stop);
        EXPECT_EQ(counter.load(), 1);

        {
            CallbackGuard guard2(counter, stop);
            EXPECT_EQ(counter.load(), 2);
        }

        EXPECT_EQ(counter.load(), 1);
    }
    EXPECT_EQ(counter.load(), 0);
}

// =============================================================================
// shouldSkip() behavior
// =============================================================================

TEST(CallbackGuardTest, ShouldSkip_ReturnsFalseWhenNotStopping) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{false};

    CallbackGuard guard(counter, stop);
    EXPECT_FALSE(guard.shouldSkip());
}

TEST(CallbackGuardTest, ShouldSkip_ReturnsTrueWhenStopping) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{true};

    CallbackGuard guard(counter, stop);
    EXPECT_TRUE(guard.shouldSkip());
}

TEST(CallbackGuardTest, ShouldSkip_CapturedAtConstruction) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{false};

    CallbackGuard guard(counter, stop);
    EXPECT_FALSE(guard.shouldSkip());

    // Changing the flag after construction should not affect the guard
    stop = true;
    EXPECT_FALSE(guard.shouldSkip());
}

TEST(CallbackGuardTest, ShouldSkip_StillIncrementsCounterWhenStopping) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{true};

    {
        CallbackGuard guard(counter, stop);
        EXPECT_TRUE(guard.shouldSkip());
        // Counter is still incremented even when skip is true
        // (needed so disconnect() spin-wait can see in-flight callbacks)
        EXPECT_EQ(counter.load(), 1);
    }
    EXPECT_EQ(counter.load(), 0);
}

// =============================================================================
// Thread safety
// =============================================================================

TEST(CallbackGuardTest, ConcurrentGuards_NoDataRace) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{false};

    constexpr int NUM_THREADS = 8;
    constexpr int ITERATIONS = 1000;

    std::vector<std::thread> threads;
    threads.reserve(NUM_THREADS);

    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&counter, &stop]() {
            for (int i = 0; i < ITERATIONS; ++i) {
                CallbackGuard guard(counter, stop);
                // Counter should always be >= 1 while guard is alive
                EXPECT_GE(counter.load(), 1);
            }
        });
    }

    for (auto& thread : threads) {
        thread.join();
    }

    // All guards destroyed, counter should be back to zero
    EXPECT_EQ(counter.load(), 0);
}

TEST(CallbackGuardTest, ConcurrentGuards_WithStopFlag) {
    std::atomic<int> counter{0};
    std::atomic<bool> stop{false};

    constexpr int NUM_THREADS = 4;
    constexpr int ITERATIONS = 500;

    std::vector<std::thread> threads;
    threads.reserve(NUM_THREADS);

    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&counter, &stop, t]() {
            for (int i = 0; i < ITERATIONS; ++i) {
                // Toggle stop flag from one thread to exercise the race
                if (t == 0 && i == ITERATIONS / 2) {
                    stop = true;
                }
                CallbackGuard guard(counter, stop);
                // shouldSkip() should be consistent within a single guard
                [[maybe_unused]] bool skip = guard.shouldSkip();
            }
        });
    }

    for (auto& thread : threads) {
        thread.join();
    }

    EXPECT_EQ(counter.load(), 0);
}

} // namespace
} // namespace tracker
