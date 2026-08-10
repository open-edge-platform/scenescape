// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <thread>

namespace tracker {

/**
 * @brief Callable that returns the current NTP-adjusted UTC time.
 *
 * Use makeSystemClock() for the unadjusted default. Inject a lambda in
 * tests to control time without spawning real threads.
 */
using ClockFn = std::function<std::chrono::system_clock::time_point()>;

/**
 * @brief Return a ClockFn that delegates to system_clock::now().
 *
 * This is the default used when no NTP server is configured. The
 * returned function is stateless.
 */
ClockFn makeSystemClock();

/**
 * @brief Periodically synchronises a clock offset against an NTP server.
 *
 * Sends a minimal 48-byte NTP request (RFC 5905 client mode) to the
 * configured server every @p interval_s seconds and atomically updates
 * the measured offset. On failure the previous offset is preserved and
 * a warning is logged.
 *
 * Usage:
 *   NtpClock ntp;
 *   ntp.start("pool.ntp.org", 300);           // background sync
 *   MessageHandler h(..., ntp.asClockFn());   // inject into handler
 *   // ...
 *   ntp.stop();                               // clean shutdown
 *
 * Thread-safety: all public methods are thread-safe.
 */
class NtpClock {
public:
    NtpClock() = default;
    ~NtpClock();

    // Non-copyable, non-movable (owns a thread)
    NtpClock(const NtpClock&) = delete;
    NtpClock& operator=(const NtpClock&) = delete;
    NtpClock(NtpClock&&) = delete;
    NtpClock& operator=(NtpClock&&) = delete;

    /**
     * @brief Start background NTP sync thread.
     *
     * Performs an initial sync immediately then repeats every @p interval_s
     * seconds. Calling start() twice without an intervening stop() is safe
     * — the second call is a no-op.
     *
     * @param host  NTP server hostname or IP (e.g. "pool.ntp.org")
     * @param interval_s  Re-sync interval in seconds
     */
    void start(const std::string& host, int interval_s);

    /**
     * @brief Stop background sync thread and join it.
     *
     * Safe to call even if start() was never called.
     */
    void stop();

    /**
     * @brief Return NTP-adjusted current time.
     *
     * Inline to avoid function-call overhead on the hot path; the body is a
     * single atomic load plus a nanosecond addition to system_clock::now().
     */
    [[nodiscard]] inline std::chrono::system_clock::time_point now() const {
        return std::chrono::system_clock::now() +
               std::chrono::nanoseconds(offset_ns_.load(std::memory_order_relaxed));
    }

    /**
     * @brief Return a ClockFn that calls now() on this instance.
     *
     * The returned function holds a raw pointer to *this. Ensure the
     * NtpClock outlives any object that uses the ClockFn.
     */
    [[nodiscard]] ClockFn asClockFn();

    /**
     * @brief Return the current NTP offset in seconds (for logging/metrics).
     */
    [[nodiscard]] double offset() const {
        return static_cast<double>(offset_ns_.load(std::memory_order_relaxed)) / 1.0e9;
    }

    /**
     * @brief Return true if at least one successful NTP sync has completed.
     *
     * Once set to true this flag is never reset, even after consecutive sync
     * failures. The last known-good offset is retained intentionally: a stale
     * but previously-accurate correction is safer than suddenly falling back
     * to a potentially skewed system clock.
     *
     * Future improvement: add a staleness threshold that resets this flag
     * (and zeroes the offset) when no successful sync has occurred for a
     * configurable duration.
     */
    [[nodiscard]] bool synced() const { return synced_.load(std::memory_order_relaxed); }

private:
    void syncOnce(const std::string& host);
    void runLoop(const std::string& host, int interval_s);

    std::atomic<int64_t> offset_ns_{0}; ///< NTP offset in nanoseconds (avoids conversion in now())
    std::atomic<bool> synced_{false};   ///< True after first successful sync; see synced() doc
    std::atomic<bool> stop_requested_{false};
    std::atomic<bool> running_{false};
    std::thread sync_thread_;
    std::mutex cv_mutex_;
    std::condition_variable cv_;
};

/**
 * @brief Parse ISO 8601 UTC timestamp to system_clock time_point.
 *
 * Expected format: "YYYY-MM-DDTHH:MM:SS[.fff]Z"
 *   - 'T' separator between date and time (required)
 *   - Optional fractional seconds (up to millisecond precision)
 *   - 'Z' suffix indicates UTC timezone (required)
 *
 * Uses sscanf for compact parsing and C++20 chrono calendar types for
 * portable date validation and UTC conversion.
 *
 * @param timestamp_iso ISO 8601 timestamp string
 * @return Parsed time_point with millisecond precision, or nullopt on failure
 */
std::optional<std::chrono::sys_time<std::chrono::milliseconds>>
parseTimestamp(const std::string& timestamp_iso);

/**
 * @brief Format system_clock time_point as ISO 8601 UTC string.
 *
 * Output format: "YYYY-MM-DDTHH:MM:SS.fffZ" (millisecond precision, UTC).
 *
 * @param tp Time point to format
 * @return ISO 8601 formatted string
 */
std::string formatTimestamp(std::chrono::system_clock::time_point tp);

/**
 * @brief Internal NTP query implementation — exposed for unit testing.
 *
 * Performs a single NTP exchange with the given host:port and returns the
 * clock offset in seconds (positive = local clock is behind the server).
 * Returns nullopt on any network error, KoD response, clock discontinuity.
 */
namespace detail {
std::optional<double> queryNtp(const std::string& host, int port = 123);
} // namespace detail

} // namespace tracker
