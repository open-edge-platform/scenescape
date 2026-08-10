// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include "logger.hpp"
#include "time_utils.hpp"

#include <arpa/inet.h>
#include <array>
#include <chrono>
#include <cstring>
#include <netinet/in.h>
#include <string>
#include <sys/socket.h>
#include <sys/time.h>
#include <thread>
#include <unistd.h>

namespace tracker {
namespace {

using namespace std::chrono;

/**
 * @brief Helper to build a known UTC time_point for test assertions.
 */
sys_time<milliseconds> make_utc(int y, unsigned m, unsigned d, int h, int min, int s, int ms = 0) {
    auto ymd = year{y} / month{m} / day{d};
    return sys_days{ymd} + hours{h} + minutes{min} + seconds{s} + milliseconds{ms};
}

//
// Parameterized tests for valid timestamps
//
struct ValidTimestampTestCase {
    std::string name;
    std::string input;
    sys_time<milliseconds> expected;
};

void PrintTo(const ValidTimestampTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class ValidTimestampTest : public ::testing::TestWithParam<ValidTimestampTestCase> {};

TEST_P(ValidTimestampTest, ParsesCorrectly) {
    const auto& tc = GetParam();
    auto result = parseTimestamp(tc.input);
    ASSERT_TRUE(result.has_value()) << "Failed to parse: " << tc.input;
    EXPECT_EQ(*result, tc.expected) << "Mismatch for: " << tc.input;
}

INSTANTIATE_TEST_SUITE_P(
    ValidTimestamps, ValidTimestampTest,
    ::testing::Values(ValidTimestampTestCase{"StandardWithMillis", "2026-01-27T12:00:00.482Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 482)},
                      ValidTimestampTestCase{"ZeroMillis", "2026-01-27T12:00:00.000Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 0)},
                      ValidTimestampTestCase{"NoFractionalSeconds", "2026-01-27T12:00:00Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 0)},
                      ValidTimestampTestCase{"OneDigitFraction", "2026-01-27T12:00:00.1Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 100)},
                      ValidTimestampTestCase{"TwoDigitFraction", "2026-01-27T12:00:00.12Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 120)},
                      ValidTimestampTestCase{"ThreeDigitFraction", "2026-01-27T12:00:00.123Z",
                                             make_utc(2026, 1, 27, 12, 0, 0, 123)},
                      ValidTimestampTestCase{"Midnight", "2026-01-01T00:00:00.000Z",
                                             make_utc(2026, 1, 1, 0, 0, 0, 0)},
                      ValidTimestampTestCase{"EndOfDay", "2026-12-31T23:59:59.999Z",
                                             make_utc(2026, 12, 31, 23, 59, 59, 999)},
                      ValidTimestampTestCase{"LeapYear", "2024-02-29T12:00:00.000Z",
                                             make_utc(2024, 2, 29, 12, 0, 0, 0)},
                      ValidTimestampTestCase{"Epoch", "1970-01-01T00:00:00.000Z",
                                             make_utc(1970, 1, 1, 0, 0, 0, 0)}),
    [](const ::testing::TestParamInfo<ValidTimestampTestCase>& info) { return info.param.name; });

//
// Parameterized tests for invalid timestamps
//
struct InvalidTimestampTestCase {
    std::string name;
    std::string input;
};

void PrintTo(const InvalidTimestampTestCase& tc, std::ostream* os) {
    *os << tc.name;
}

class InvalidTimestampTest : public ::testing::TestWithParam<InvalidTimestampTestCase> {};

TEST_P(InvalidTimestampTest, ReturnsNullopt) {
    const auto& tc = GetParam();
    auto result = parseTimestamp(tc.input);
    EXPECT_FALSE(result.has_value()) << "Expected failure for: " << tc.input;
}

INSTANTIATE_TEST_SUITE_P(
    InvalidTimestamps, InvalidTimestampTest,
    ::testing::Values(InvalidTimestampTestCase{"Empty", ""},
                      InvalidTimestampTestCase{"Garbage", "not-a-timestamp"},
                      InvalidTimestampTestCase{"MissingZ", "2026-01-27T12:00:00.000"},
                      InvalidTimestampTestCase{"SpaceSeparator", "2026-01-27 12:00:00.000Z"},
                      InvalidTimestampTestCase{"DateOnly", "2026-01-27"},
                      InvalidTimestampTestCase{"InvalidMonth", "2026-13-01T12:00:00Z"},
                      InvalidTimestampTestCase{"InvalidDay", "2026-02-30T12:00:00Z"},
                      InvalidTimestampTestCase{"InvalidHour", "2026-01-27T25:00:00Z"},
                      InvalidTimestampTestCase{"NonLeapYear", "2025-02-29T12:00:00Z"},
                      InvalidTimestampTestCase{"TrailingJunk", "2026-01-27T12:00:00.000Zextra"}),
    [](const ::testing::TestParamInfo<InvalidTimestampTestCase>& info) { return info.param.name; });

//
// Round-trip consistency: parse then format should reproduce input
//
TEST(TimestampRoundTrip, CanonicalFormat) {
    const std::string input = "2026-06-15T08:30:45.123Z";
    auto result = parseTimestamp(input);
    ASSERT_TRUE(result.has_value());

    // Round-trip through formatTimestamp
    auto formatted = formatTimestamp(*result);
    EXPECT_EQ(formatted, input);
}

//
// formatTimestamp tests
//
TEST(FormatTimestamp, ProducesIso8601WithMillis) {
    using namespace std::chrono;
    auto tp = sys_days{2026y / January / 1} + 0h + 0min + 0s;
    EXPECT_EQ(formatTimestamp(tp), "2026-01-01T00:00:00.000Z");
}

TEST(FormatTimestamp, PreservesMilliseconds) {
    using namespace std::chrono;
    auto tp = sys_days{2026y / March / 15} + 14h + 30min + 45s + 789ms;
    EXPECT_EQ(formatTimestamp(tp), "2026-03-15T14:30:45.789Z");
}

//
// ClockFn / makeSystemClock tests
//

TEST(MakeSystemClock, ReturnsTimeCloseToNow) {
    using namespace std::chrono;
    auto clock = makeSystemClock();
    auto before = system_clock::now();
    auto result = clock();
    auto after = system_clock::now();

    EXPECT_GE(result, before);
    EXPECT_LE(result, after + 10ms); // allow tiny scheduling slack
}

TEST(MakeSystemClock, MultipleCalls_ReturnIncreasingTime) {
    auto clock = makeSystemClock();
    auto t1 = clock();
    auto t2 = clock();
    EXPECT_LE(t1, t2);
}

//
// NtpClock tests
//

// Fixture initialises the logger so that LOG_WARN/LOG_INFO calls inside
// NtpClock::syncOnce() don't dereference a null quill::Logger*.
class NtpClockTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }
};

TEST_F(NtpClockTest, StopBeforeStart_DoesNotCrash) {
    NtpClock clock;
    clock.stop(); // should be a no-op
}

TEST_F(NtpClockTest, DefaultOffset_IsZero) {
    NtpClock clock;
    EXPECT_DOUBLE_EQ(clock.offset(), 0.0);
}

TEST_F(NtpClockTest, DefaultSynced_IsFalse) {
    // Before any sync attempt, synced() must be false so that the first
    // failure logs "no offset available yet" rather than "keeping previous offset".
    NtpClock clock;
    EXPECT_FALSE(clock.synced());
}

TEST_F(NtpClockTest, FailedFirstSync_LeavesOffsetZeroAndSyncedFalse) {
    // start() with an unreachable address; wait long enough for the first
    // syncOnce() attempt to complete (socket timeout = 2 s, but connect to
    // 127.0.0.2 with no listener should reject immediately).
    NtpClock clock;
    clock.start("127.0.0.2", 600); // interval=600s so only one attempt fires
    // The thread calls syncOnce once immediately then blocks on the CV.
    // stop() signals the CV and joins before we check.
    clock.stop();

    EXPECT_FALSE(clock.synced());
    EXPECT_DOUBLE_EQ(clock.offset(), 0.0);
}

TEST_F(NtpClockTest, NowWithZeroOffset_MatchesSystemClock) {
    using namespace std::chrono;
    NtpClock clock; // offset = 0.0 by default
    auto before = system_clock::now();
    auto result = clock.now();
    auto after = system_clock::now();

    EXPECT_GE(result, before);
    EXPECT_LE(result, after + 10ms);
}

TEST_F(NtpClockTest, AsClockFn_UseableAsClockFn) {
    using namespace std::chrono;
    NtpClock ntp;
    ClockFn fn = ntp.asClockFn();

    auto before = system_clock::now();
    auto result = fn();
    auto after = system_clock::now();

    EXPECT_GE(result, before);
    EXPECT_LE(result, after + 10ms);
}

// NtpClock offset application is verified indirectly: the now() contract is that
// it returns system_clock::now() + offset_ns. With offset_ns = 0 (default, no sync),
// the behaviour is identical to system_clock::now() (tested above).
// Offset application with non-zero values is covered in message_handler_test.cpp
// via lambda ClockFn injection, which exercises the full lag-check path.

TEST_F(NtpClockTest, NowDelta_StaysNearZeroWithNoSync) {
    using namespace std::chrono;
    NtpClock clock;
    auto t1 = clock.now();
    auto t2 = system_clock::now();
    auto delta = duration<double>(t2 - t1).count();
    EXPECT_NEAR(delta, 0.0, 0.01); // within 10 ms
}

TEST_F(NtpClockTest, DestructorWithActiveThread_DoesNotHang) {
    // start() with a loopback address that has no NTP listener — syncOnce
    // will fail quickly (connect/recv timeout). The destructor must join cleanly.
    {
        NtpClock clock;
        clock.start("127.0.0.2", 600);
        // destructor calls stop() and joins the thread
    }
    SUCCEED(); // reaching here means no deadlock
}

// ---------------------------------------------------------------------------
// FakeNtpServer — minimal UDP NTP server for unit testing queryNtp
// ---------------------------------------------------------------------------

/// NTP epoch offset: seconds between 1900-01-01 and 1970-01-01
constexpr uint32_t kNtpUnixDelta = 2208988800U;

/**
 * @brief Build a 48-byte NTP reply packet with the given stratum and server timestamps.
 *
 * @param stratum  NTP stratum byte (0 = KoD, 1-15 = valid, 16 = unsynchronized)
 * @param t2_unix  Server receive timestamp (Unix seconds, double)
 * @param t3_unix  Server transmit timestamp (Unix seconds, double)
 */
std::array<uint8_t, 48> make_ntp_reply(uint8_t stratum, double t2_unix, double t3_unix) {
    std::array<uint8_t, 48> pkt{};
    pkt[0] = 0x24; // LI=0, VN=4, Mode=4 (server)
    pkt[1] = stratum;

    auto encode = [](uint8_t* dst, double unix_time) {
        double ntp_time = unix_time + static_cast<double>(kNtpUnixDelta);
        uint32_t sec = static_cast<uint32_t>(ntp_time);
        uint32_t frac = static_cast<uint32_t>((ntp_time - sec) * 4294967296.0);
        // Write big-endian (network byte order)
        dst[0] = (sec >> 24) & 0xFF;
        dst[1] = (sec >> 16) & 0xFF;
        dst[2] = (sec >> 8) & 0xFF;
        dst[3] = sec & 0xFF;
        dst[4] = (frac >> 24) & 0xFF;
        dst[5] = (frac >> 16) & 0xFF;
        dst[6] = (frac >> 8) & 0xFF;
        dst[7] = frac & 0xFF;
    };

    encode(pkt.data() + 32, t2_unix); // T2: server receive timestamp
    encode(pkt.data() + 40, t3_unix); // T3: server transmit timestamp
    return pkt;
}

/**
 * @brief Minimal single-shot fake NTP UDP server for testing queryNtp.
 *
 * Binds on 127.0.0.1:0 (OS picks a free port), waits for one incoming
 * NTP request, and replies with the injected packet. Runs in a background
 * thread. Call join() before destroying.
 */
class FakeNtpServer {
public:
    FakeNtpServer() {
        sock_ = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        EXPECT_GE(sock_, 0);

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        addr.sin_port = 0; // OS picks free port
        EXPECT_EQ(bind(sock_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)), 0);

        socklen_t len = sizeof(addr);
        EXPECT_EQ(getsockname(sock_, reinterpret_cast<sockaddr*>(&addr), &len), 0);
        port_ = ntohs(addr.sin_port);

        // Bound receive timeout so the serve thread never hangs indefinitely
        // if the client request never arrives (e.g. early test failure).
        timeval tv{};
        tv.tv_sec = 5;
        tv.tv_usec = 0;
        setsockopt(sock_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    }

    ~FakeNtpServer() {
        // Ensure the serve thread finishes before the socket is closed.
        // A receive timeout on the socket (set in the constructor) guarantees
        // the thread unblocks even if the client never sends a request.
        if (thread_.joinable())
            thread_.join();
        if (sock_ >= 0)
            close(sock_);
    }

    int port() const { return port_; }

    /// Start background thread that receives one request and sends reply.
    void serve_once(std::array<uint8_t, 48> reply) {
        thread_ = std::thread([this, reply]() {
            uint8_t buf[48];
            sockaddr_in client{};
            socklen_t clen = sizeof(client);
            ssize_t n =
                recvfrom(sock_, buf, sizeof(buf), 0, reinterpret_cast<sockaddr*>(&client), &clen);
            if (n > 0) {
                sendto(sock_, reply.data(), 48, 0, reinterpret_cast<sockaddr*>(&client), clen);
            }
        });
    }

    void join() {
        if (thread_.joinable())
            thread_.join();
    }

private:
    int sock_ = -1;
    int port_ = 0;
    std::thread thread_;
};

// ---------------------------------------------------------------------------
// queryNtp — stratum guard tests
// ---------------------------------------------------------------------------

class QueryNtpTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }
};

TEST_F(QueryNtpTest, KoD_Stratum0_ReturnsNullopt) {
    double now =
        std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    FakeNtpServer srv;
    srv.serve_once(make_ntp_reply(0, now, now));
    auto result = detail::queryNtp("127.0.0.1", srv.port());
    srv.join();
    EXPECT_FALSE(result.has_value()) << "Stratum 0 (KoD) should be rejected";
}

TEST_F(QueryNtpTest, ValidStratum1_ReturnsOffset) {
    double now =
        std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    FakeNtpServer srv;
    srv.serve_once(make_ntp_reply(1, now, now));
    auto result = detail::queryNtp("127.0.0.1", srv.port());
    srv.join();
    ASSERT_TRUE(result.has_value()) << "Stratum 1 should be accepted";
    EXPECT_NEAR(*result, 0.0, 0.5); // on loopback, offset ≈ 0
}

TEST_F(QueryNtpTest, ValidStratum15_ReturnsOffset) {
    double now =
        std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    FakeNtpServer srv;
    srv.serve_once(make_ntp_reply(15, now, now));
    auto result = detail::queryNtp("127.0.0.1", srv.port());
    srv.join();
    ASSERT_TRUE(result.has_value()) << "Stratum 15 (upper valid boundary) should be accepted";
    EXPECT_NEAR(*result, 0.0, 0.5);
}

TEST_F(QueryNtpTest, InvalidStratum17_ReturnsNullopt) {
    // Stratum > 16 is undefined / garbage in RFC 5905
    double now =
        std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    FakeNtpServer srv;
    srv.serve_once(make_ntp_reply(17, now, now));
    auto result = detail::queryNtp("127.0.0.1", srv.port());
    srv.join();
    EXPECT_FALSE(result.has_value()) << "Stratum 17 (undefined) should be rejected";
}

TEST_F(QueryNtpTest, ZeroServerTimestamp_ReturnsNullopt) {
    // A zero NTP timestamp (t2_sec=0 / t3_sec=0) predates the Unix epoch.
    // Subtracting kNtpUnixDeltaSeconds would underflow uint32_t and produce a
    // huge Unix time, corrupting the offset calculation. Must be rejected.
    FakeNtpServer srv;
    std::array<uint8_t, 48> pkt{};
    pkt[0] = 0x24; // LI=0, VN=4, Mode=4 (server)
    pkt[1] = 1;    // stratum 1 — valid, so the only rejection cause is the zero timestamps
    // T2 and T3 bytes (offsets 32-47) remain zero (uninitialized server response)
    srv.serve_once(pkt);
    auto result = detail::queryNtp("127.0.0.1", srv.port());
    srv.join();
    EXPECT_FALSE(result.has_value())
        << "Zero server timestamps predate Unix epoch and must be rejected";
}

// NOTE: The T4 < T1 clock-discontinuity guard cannot be reliably triggered
// via the fake server because T1 and T4 are real system_clock captures that
// bracket the actual socket send/recv. Testing this path requires injecting
// a controllable clock into queryNtp — deferred as a future refactor.

// ---------------------------------------------------------------------------
// queryNtp — end-to-end offset calculation (simulated time drift)
// ---------------------------------------------------------------------------

// Parameterized test: verifies offset calculation for both directions of clock skew.
// server_bias > 0: local clock is behind NTP (positive offset expected).
// server_bias < 0: local clock is ahead of NTP (negative offset expected).
class OffsetCalculationTest : public QueryNtpTest, public ::testing::WithParamInterface<double> {};

TEST_P(OffsetCalculationTest, OffsetCalculation_MatchesServerBias) {
    double bias = GetParam();
    double now =
        std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    FakeNtpServer srv;
    srv.serve_once(make_ntp_reply(1, now + bias, now + bias));
    auto result = detail::queryNtp("127.0.0.1", srv.port());
    srv.join();
    ASSERT_TRUE(result.has_value());
    EXPECT_NEAR(*result, bias, 0.5) << "Expected offset ~ " << bias << "s";
}

INSTANTIATE_TEST_SUITE_P(OffsetDirections, OffsetCalculationTest, ::testing::Values(5.0, -5.0));

} // namespace
} // namespace tracker
