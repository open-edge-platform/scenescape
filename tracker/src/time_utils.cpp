// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "time_utils.hpp"
#include "logger.hpp"

#include <arpa/inet.h>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <format>
#include <netdb.h>
#include <string_view>
#include <sys/socket.h>
#include <unistd.h>

namespace tracker {

// ---------------------------------------------------------------------------
// ClockFn factory
// ---------------------------------------------------------------------------

ClockFn makeSystemClock() {
    return []() { return std::chrono::system_clock::now(); };
}

// ---------------------------------------------------------------------------
// NtpClock
// ---------------------------------------------------------------------------

namespace {

/// NTP epoch is 1 January 1900; Unix epoch is 1 January 1970.
constexpr uint32_t kNtpUnixDeltaSeconds = 2208988800U;
constexpr int kNtpPort = 123;
constexpr int kNtpPacketSize = 48;
constexpr int kNtpSocketTimeoutMs = 2000;

/**
 * @brief Perform a single NTP exchange and return the measured offset in seconds.
 *
 * Sends a minimal client-mode NTP request (RFC 5905) and computes the offset
 * using the standard four-timestamp formula:
 *   offset = ((T2 - T1) + (T3 - T4)) / 2
 *
 * @param host NTP server hostname or IP
 * @return Offset in seconds (positive = local clock is behind), or nullopt on error
 */
std::optional<double> queryNtp(const std::string& host) {
    // Resolve hostname
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;
    hints.ai_protocol = IPPROTO_UDP;

    addrinfo* res = nullptr;
    if (getaddrinfo(host.c_str(), std::to_string(kNtpPort).c_str(), &hints, &res) != 0 ||
        res == nullptr) {
        return std::nullopt;
    }
    // RAII cleanup
    struct AddrGuard {
        addrinfo* p;
        ~AddrGuard() { freeaddrinfo(p); }
    } guard{res};

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        return std::nullopt;
    }

    // Set receive timeout
    timeval tv{};
    tv.tv_sec = kNtpSocketTimeoutMs / 1000;
    tv.tv_usec = (kNtpSocketTimeoutMs % 1000) * 1000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    // Build NTP request packet (LI=0, VN=4, Mode=3 client)
    uint8_t packet[kNtpPacketSize] = {};
    packet[0] = 0x23; // LI=0, VN=4, Mode=3

    // Capture T1 (originate timestamp) just before sending
    auto t1 = std::chrono::system_clock::now();

    if (sendto(sock, packet, kNtpPacketSize, 0, res->ai_addr, res->ai_addrlen) < 0) {
        close(sock);
        return std::nullopt;
    }

    uint8_t reply[kNtpPacketSize] = {};
    ssize_t n = recv(sock, reply, kNtpPacketSize, 0);
    // Capture T4 (destination timestamp) immediately after receive
    auto t4 = std::chrono::system_clock::now();
    close(sock);

    if (n < kNtpPacketSize) {
        return std::nullopt;
    }

    // Extract T2 (receive timestamp at server) from bytes 32-39
    uint32_t t2_sec = ntohl(static_cast<uint32_t>(reply[32]) << 24 |
                            static_cast<uint32_t>(reply[33]) << 16 |
                            static_cast<uint32_t>(reply[34]) << 8 | reply[35]);
    uint32_t t2_frac = ntohl(static_cast<uint32_t>(reply[36]) << 24 |
                             static_cast<uint32_t>(reply[37]) << 16 |
                             static_cast<uint32_t>(reply[38]) << 8 | reply[39]);

    // Extract T3 (transmit timestamp at server) from bytes 40-47
    uint32_t t3_sec = ntohl(static_cast<uint32_t>(reply[40]) << 24 |
                            static_cast<uint32_t>(reply[41]) << 16 |
                            static_cast<uint32_t>(reply[42]) << 8 | reply[43]);
    uint32_t t3_frac = ntohl(static_cast<uint32_t>(reply[44]) << 24 |
                             static_cast<uint32_t>(reply[45]) << 16 |
                             static_cast<uint32_t>(reply[46]) << 8 | reply[47]);

    // Convert NTP timestamps to seconds since Unix epoch
    auto ntp_to_unix = [](uint32_t sec, uint32_t frac) -> double {
        return static_cast<double>(sec - kNtpUnixDeltaSeconds) +
               static_cast<double>(frac) / 4294967296.0;
    };

    double d_t1 = std::chrono::duration<double>(t1.time_since_epoch()).count();
    double d_t2 = ntp_to_unix(t2_sec, t2_frac);
    double d_t3 = ntp_to_unix(t3_sec, t3_frac);
    double d_t4 = std::chrono::duration<double>(t4.time_since_epoch()).count();

    // RFC 5905 offset formula: offset = ((T2 - T1) + (T3 - T4)) / 2
    return ((d_t2 - d_t1) + (d_t3 - d_t4)) / 2.0;
}

} // namespace

NtpClock::~NtpClock() {
    stop();
}

void NtpClock::start(const std::string& host, int interval_s) {
    if (running_.exchange(true)) {
        return; // already running
    }
    stop_requested_.store(false);
    sync_thread_ = std::thread([this, host, interval_s]() { runLoop(host, interval_s); });
}

void NtpClock::stop() {
    if (!running_.load()) {
        return;
    }
    {
        std::lock_guard<std::mutex> lock(cv_mutex_);
        stop_requested_.store(true);
    }
    cv_.notify_all();
    if (sync_thread_.joinable()) {
        sync_thread_.join();
    }
    running_.store(false);
}

void NtpClock::syncOnce(const std::string& host) {
    auto result = queryNtp(host);
    if (result) {
        offset_s_.store(*result, std::memory_order_relaxed);
        synced_.store(true, std::memory_order_relaxed);
        LOG_INFO("NTP sync: offset={:.6f}s (server={})", *result, host);
    } else if (synced_.load(std::memory_order_relaxed)) {
        LOG_WARN("NTP sync failed — keeping previous offset={:.6f}s (server={})",
                 offset_s_.load(std::memory_order_relaxed), host);
    } else {
        LOG_WARN("NTP sync failed — no offset available yet, using raw system clock (server={})",
                 host);
    }
}

void NtpClock::runLoop(const std::string& host, int interval_s) {
    // Initial sync before waiting
    syncOnce(host);

    while (!stop_requested_.load()) {
        std::unique_lock<std::mutex> lock(cv_mutex_);
        cv_.wait_for(lock, std::chrono::seconds(interval_s),
                     [this] { return stop_requested_.load(); });
        if (stop_requested_.load()) {
            break;
        }
        lock.unlock();
        syncOnce(host);
    }
}

std::chrono::system_clock::time_point NtpClock::now() const {
    using namespace std::chrono;
    auto raw = system_clock::now();
    // Convert double seconds offset to nanoseconds for precision
    auto offset_ns = duration_cast<nanoseconds>(duration<double>(offset_s_.load(std::memory_order_relaxed)));
    return raw + offset_ns;
}

ClockFn NtpClock::asClockFn() {
    return [this]() { return now(); };
}

// ---------------------------------------------------------------------------
// parseTimestamp / formatTimestamp
// ---------------------------------------------------------------------------

std::optional<std::chrono::sys_time<std::chrono::milliseconds>>
parseTimestamp(const std::string& timestamp_iso) {
    using namespace std::chrono;

    int y, mo, d, h, mi, s, n = 0;
    if (std::sscanf(timestamp_iso.c_str(), "%d-%d-%dT%d:%d:%d%n", &y, &mo, &d, &h, &mi, &s, &n) !=
            6 ||
        n == 0) {
        return std::nullopt;
    }

    // Validate time ranges
    if (h < 0 || h > 23 || mi < 0 || mi > 59 || s < 0 || s > 59) {
        return std::nullopt;
    }

    // Parse optional fractional seconds, then require trailing 'Z'
    std::string_view sv(timestamp_iso);
    size_t pos = static_cast<size_t>(n);
    int millis = 0;
    if (pos < sv.size() && sv[pos] == '.') {
        ++pos;
        int digits = 0;
        int frac = 0;
        while (pos < sv.size() && sv[pos] >= '0' && sv[pos] <= '9') {
            if (digits < 3) {
                frac = frac * 10 + (sv[pos] - '0');
            }
            ++digits;
            ++pos;
        }
        if (digits == 0)
            return std::nullopt;
        // Scale to milliseconds based on digits parsed (up to 3)
        for (int i = digits; i < 3; ++i)
            frac *= 10;
        millis = frac;
    }

    if (pos >= sv.size() || sv[pos] != 'Z' || pos + 1 != sv.size()) {
        return std::nullopt;
    }

    // Validate date via C++20 calendar types
    auto ymd = year{y} / month{static_cast<unsigned>(mo)} / day{static_cast<unsigned>(d)};
    if (!ymd.ok()) {
        return std::nullopt;
    }

    return sys_days{ymd} + hours{h} + minutes{mi} + seconds{s} + milliseconds{millis};
}

std::string formatTimestamp(std::chrono::system_clock::time_point tp) {
    using namespace std::chrono;
    auto ms = floor<milliseconds>(tp);
    auto sec = floor<seconds>(ms);
    return std::format("{:%Y-%m-%dT%H:%M:%S}.{:03d}Z", sec, (ms - sec).count());
}

} // namespace tracker
